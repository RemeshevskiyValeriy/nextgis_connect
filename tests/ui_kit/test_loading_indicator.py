# NextGIS Connect
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

from qgis.PyQt.QtCore import QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QPalette

from nextgis_connect.ui_kit.buttons import CancelButton
from nextgis_connect.ui_kit.graphics.loading_indicator import (
    LoadingIndicatorRenderer,
)
from nextgis_connect.ui_kit.widgets.loading_indicator import (
    LoadingIndicatorIconAnimator,
    LoadingIndicatorWidget,
)


def _visible_pixel_count(pixmap) -> int:
    image = pixmap.toImage()
    count = 0

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                count += 1

    return count


class _PainterProbe:
    def __init__(self) -> None:
        self.arc_calls = []
        self.ellipse_calls = []
        self.pen_cap_styles = []

    def save(self) -> None:
        pass

    def restore(self) -> None:
        pass

    def setRenderHint(self, _hint, _enabled) -> None:
        pass

    def setPen(self, pen) -> None:
        self.pen_cap_styles.append(pen.capStyle())

    def setBrush(self, _brush) -> None:
        pass

    def drawArc(self, rect, start_angle, span_angle) -> None:
        self.arc_calls.append((rect, start_angle, span_angle))

    def drawEllipse(self, rect) -> None:
        self.ellipse_calls.append(rect)


def test_loading_indicator_renderer_draws_visible_frame(qgis_app) -> None:
    del qgis_app

    pixmap = LoadingIndicatorRenderer().pixmap(
        QSize(18, 18),
        angle=0.0,
    )

    assert not pixmap.isNull()
    assert _visible_pixel_count(pixmap) > 0


def test_loading_indicator_renderer_draws_track_as_arc() -> None:
    painter = _PainterProbe()

    LoadingIndicatorRenderer().paint(
        painter,
        QRectF(0.0, 0.0, 18.0, 18.0),
        palette=QPalette(),
        angle=0.0,
    )

    assert len(painter.arc_calls) == 2
    assert painter.ellipse_calls == []
    assert painter.pen_cap_styles == [
        Qt.PenCapStyle.FlatCap,
        Qt.PenCapStyle.RoundCap,
    ]
    arc_start_angle = round(
        LoadingIndicatorRenderer._ARC_START_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )
    arc_span_angle = round(
        LoadingIndicatorRenderer.ARC_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )
    track_start_angle = arc_start_angle + arc_span_angle
    track_span_angle = (
        round(
            LoadingIndicatorRenderer.TRACK_DEGREES
            * LoadingIndicatorRenderer._QT_ANGLE_UNIT
        )
        - arc_span_angle
    )
    overlap_span_angle = round(
        LoadingIndicatorRenderer.ARC_OVERLAP_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )
    visible_arc_start_angle = arc_start_angle
    visible_arc_span_angle = arc_span_angle + overlap_span_angle

    assert painter.arc_calls[0][1] == track_start_angle
    assert painter.arc_calls[0][2] == track_span_angle
    assert painter.arc_calls[1][1] == visible_arc_start_angle
    assert painter.arc_calls[1][2] == visible_arc_span_angle


def test_loading_indicator_renderer_omits_track_at_full_progress() -> None:
    painter = _PainterProbe()

    LoadingIndicatorRenderer().paint(
        painter,
        QRectF(0.0, 0.0, 18.0, 18.0),
        palette=QPalette(),
        angle=0.0,
        arc_degrees=360.0,
    )

    assert len(painter.arc_calls) == 1
    assert painter.ellipse_calls == []
    assert painter.arc_calls[0][2] == (
        -LoadingIndicatorRenderer.TRACK_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )


def test_loading_indicator_renderer_grows_progress_clockwise() -> None:
    painter = _PainterProbe()

    LoadingIndicatorRenderer().paint(
        painter,
        QRectF(0.0, 0.0, 18.0, 18.0),
        palette=QPalette(),
        angle=0.0,
        arc_degrees=180.0,
    )

    arc_start_angle = round(
        LoadingIndicatorRenderer._ARC_START_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )
    arc_span_angle = round(180.0 * LoadingIndicatorRenderer._QT_ANGLE_UNIT)
    track_span_angle = (
        round(
            LoadingIndicatorRenderer.TRACK_DEGREES
            * LoadingIndicatorRenderer._QT_ANGLE_UNIT
        )
        - arc_span_angle
    )
    overlap_span_angle = round(
        LoadingIndicatorRenderer.ARC_OVERLAP_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )

    assert len(painter.arc_calls) == 2
    assert painter.arc_calls[0][1] == arc_start_angle - arc_span_angle
    assert painter.arc_calls[0][2] == -track_span_angle
    assert painter.arc_calls[1][1] == arc_start_angle
    assert painter.arc_calls[1][2] == -(arc_span_angle + overlap_span_angle)


def test_loading_indicator_renderer_limits_overlap_to_track_size() -> None:
    painter = _PainterProbe()

    LoadingIndicatorRenderer().paint(
        painter,
        QRectF(0.0, 0.0, 18.0, 18.0),
        palette=QPalette(),
        angle=0.0,
        arc_degrees=358.0,
    )

    full_span_angle = round(
        LoadingIndicatorRenderer.TRACK_DEGREES
        * LoadingIndicatorRenderer._QT_ANGLE_UNIT
    )
    arc_span_angle = round(358.0 * LoadingIndicatorRenderer._QT_ANGLE_UNIT)
    track_span_angle = full_span_angle - arc_span_angle
    overlap_span_angle = track_span_angle // 2

    assert len(painter.arc_calls) == 2
    assert painter.arc_calls[0][2] == -track_span_angle
    assert painter.arc_calls[1][2] == (-(arc_span_angle + overlap_span_angle))


def test_loading_indicator_renderer_rotates_arc(qgis_app) -> None:
    del qgis_app

    renderer = LoadingIndicatorRenderer()
    first_frame = renderer.pixmap(QSize(18, 18), angle=0.0).toImage()
    second_frame = renderer.pixmap(QSize(18, 18), angle=90.0).toImage()

    assert first_frame != second_frame


def test_loading_indicator_renderer_uses_theme_accent_without_selection_colors(
    qgis_app,
) -> None:
    del qgis_app

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#ff5500"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#00ff55"))

    renderer = LoadingIndicatorRenderer()
    normal_frame = renderer.pixmap(
        QSize(18, 18),
        palette=palette,
        selected=False,
    ).toImage()
    selected_frame = renderer.pixmap(
        QSize(18, 18),
        palette=palette,
        selected=True,
    ).toImage()

    assert renderer._resolved_arc_color(
        palette, selected=False
    ) == palette.color(QPalette.ColorRole.Highlight)
    assert renderer._resolved_arc_color(
        palette, selected=True
    ) == palette.color(QPalette.ColorRole.Highlight)
    assert renderer._resolved_track_color(
        palette, selected=False
    ) == renderer._resolved_track_color(palette, selected=True)
    assert normal_frame == selected_frame


def test_loading_indicator_icon_animator_tracks_state(qgis_app) -> None:
    del qgis_app

    animator = LoadingIndicatorIconAnimator(QSize(16, 16))
    animator.angle = 450.0

    assert animator.angle == 90.0
    assert not animator.current_icon().isNull()

    animator.start()
    assert animator.is_running()

    animator.stop()
    assert not animator.is_running()
    assert animator.angle == 0.0


def test_loading_indicator_widget_tracks_state(qgis_app) -> None:
    del qgis_app

    widget = LoadingIndicatorWidget(size=QSize(24, 24))

    assert widget.sizeHint() == QSize(24, 24)
    assert widget.minimumSizeHint() == QSize(24, 24)

    widget.start()
    assert widget.is_running()

    widget.stop()
    assert not widget.is_running()
    widget.deleteLater()


def test_cancel_button_resolves_material_icons(qgis_app) -> None:
    del qgis_app

    button = CancelButton()

    assert button._icon_renderer is not None
    assert button._icon_renderer.is_valid()

    button.set_waiting(True)

    assert button._icon_renderer is not None
    assert button._icon_renderer.is_valid()

    button.deleteLater()
