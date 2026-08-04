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

from typing import Optional

from qgis.PyQt.QtCore import QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPalette, QPen, QPixmap

from nextgis_connect.ui_kit.graphics.decorator import (
    NextgisDecorator,
    mix_colors,
)


class LoadingIndicatorRenderer:
    """Paint the NextGIS loading indicator.

    Render a circular track and rotating arc as an icon, pixmap, or
    directly into an existing painter.
    """

    DEFAULT_SIZE = QSize(16, 16)
    PEN_WIDTH = 2.0
    ARC_DEGREES = 90.0
    TRACK_DEGREES = 360.0
    ARC_OVERLAP_DEGREES = 4.0

    _QT_ANGLE_UNIT = 16
    _ARC_START_DEGREES = 45.0

    def __init__(
        self,
        *,
        track_color: Optional[QColor] = None,
        arc_color: Optional[QColor] = None,
        pen_width: Optional[float] = None,
    ) -> None:
        """Initialize the loading indicator renderer.

        :param track_color: Optional track color override.
        :param arc_color: Optional arc color override.
        :param pen_width: Optional indicator pen width override.
        """
        self._track_color = (
            None if track_color is None else QColor(track_color)
        )
        self._arc_color = None if arc_color is None else QColor(arc_color)
        self._pen_width = self.PEN_WIDTH if pen_width is None else pen_width

    def icon(
        self,
        size: Optional[QSize] = None,
        *,
        angle: float = 0.0,
        palette: Optional[QPalette] = None,
        device_pixel_ratio: float = 1.0,
    ) -> QIcon:
        """Return a loading indicator icon.

        :param size: Logical icon size.
        :param angle: Arc rotation angle in degrees.
        :param palette: Palette used for default colors.
        :param device_pixel_ratio: Device pixel ratio for generated pixmaps.
        :return: Loading indicator icon.
        """
        icon = QIcon(
            self.pixmap(
                size,
                angle=angle,
                palette=palette,
                device_pixel_ratio=device_pixel_ratio,
            )
        )
        icon.addPixmap(
            self.pixmap(
                size,
                angle=angle,
                palette=palette,
                device_pixel_ratio=device_pixel_ratio,
                selected=True,
            ),
            QIcon.Mode.Selected,
            QIcon.State.Off,
        )
        return icon

    def pixmap(
        self,
        size: Optional[QSize] = None,
        *,
        angle: float = 0.0,
        palette: Optional[QPalette] = None,
        device_pixel_ratio: float = 1.0,
        selected: bool = False,
    ) -> QPixmap:
        """Return a loading indicator pixmap.

        :param size: Logical pixmap size.
        :param angle: Arc rotation angle in degrees.
        :param palette: Palette used for default colors.
        :param device_pixel_ratio: Device pixel ratio for the pixmap.
        :param selected: Kept for API compatibility; colors do not change for
            selection.
        :return: Loading indicator pixmap.
        """
        logical_size = self._normalize_size(size)
        scale = max(1.0, device_pixel_ratio)
        physical_size = QSize(
            max(1, round(logical_size.width() * scale)),
            max(1, round(logical_size.height() * scale)),
        )

        pixmap = QPixmap(physical_size)
        pixmap.setDevicePixelRatio(scale)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        self.paint(
            painter,
            QRectF(0.0, 0.0, logical_size.width(), logical_size.height()),
            angle=angle,
            palette=palette,
            selected=selected,
        )
        painter.end()

        return pixmap

    def paint(
        self,
        painter: QPainter,
        rect: QRectF,
        *,
        angle: float = 0.0,
        palette: Optional[QPalette] = None,
        selected: bool = False,
        arc_degrees: Optional[float] = None,
        pen_width: Optional[float] = None,
    ) -> None:
        """Paint the loading indicator.

        :param painter: Painter used for rendering.
        :param rect: Rectangle to paint into.
        :param angle: Arc rotation angle in degrees.
        :param palette: Palette used for default colors.
        :param selected: Kept for API compatibility; colors do not change for
            selection.
        :param arc_degrees: Optional arc length in degrees.
        :param pen_width: Optional pen width for this paint call.
        """
        if rect.width() <= 0 or rect.height() <= 0:
            return

        active_pen_width = self._pen_width if pen_width is None else pen_width
        indicator_rect = self._indicator_rect(rect, active_pen_width)
        if indicator_rect.width() <= 0 or indicator_rect.height() <= 0:
            return

        active_palette = NextgisDecorator.system_palette(palette)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        arc_length = self.ARC_DEGREES if arc_degrees is None else arc_degrees
        arc_length = max(0.0, min(self.TRACK_DEGREES, arc_length))
        full_span_angle = round(self.TRACK_DEGREES * self._QT_ANGLE_UNIT)
        arc_span_angle = round(arc_length * self._QT_ANGLE_UNIT)
        track_span_angle = max(0, full_span_angle - arc_span_angle)
        overlap_span_angle = self._overlap_span_angle(track_span_angle)
        direction = self._arc_direction(arc_degrees)
        arc_start_angle = self._arc_start_angle(angle)
        signed_arc_span_angle = arc_span_angle * direction
        signed_track_span_angle = track_span_angle * direction
        signed_overlap_span_angle = overlap_span_angle * direction
        track_start_angle = arc_start_angle + signed_arc_span_angle
        visible_arc_start_angle = arc_start_angle
        visible_arc_span_angle = signed_arc_span_angle
        if abs(visible_arc_span_angle) < full_span_angle:
            visible_arc_span_angle += signed_overlap_span_angle

        track_pen = QPen(
            self._resolved_track_color(active_palette, selected=selected),
            active_pen_width,
        )
        track_pen.setCapStyle(Qt.PenCapStyle.FlatCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        if track_span_angle > 0:
            painter.drawArc(
                indicator_rect,
                track_start_angle,
                signed_track_span_angle,
            )

        arc_pen = QPen(
            self._resolved_arc_color(active_palette, selected=selected),
            active_pen_width,
        )
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        if arc_span_angle > 0:
            painter.drawArc(
                indicator_rect,
                visible_arc_start_angle,
                visible_arc_span_angle,
            )

        painter.restore()

    def _normalize_size(self, size: Optional[QSize]) -> QSize:
        if size is None or not size.isValid() or size.isEmpty():
            return QSize(self.DEFAULT_SIZE)

        return QSize(size)

    def _indicator_rect(self, rect: QRectF, pen_width: float) -> QRectF:
        side = max(0.0, min(rect.width(), rect.height()))
        left = rect.left() + (rect.width() - side) / 2.0
        top = rect.top() + (rect.height() - side) / 2.0

        indicator_rect = QRectF(left, top, side, side)
        inset = pen_width / 2.0
        indicator_rect.adjust(inset, inset, -inset, -inset)

        return indicator_rect

    def _arc_start_angle(self, angle: float) -> int:
        normalized_angle = angle % 360.0
        start_degrees = self._ARC_START_DEGREES - normalized_angle

        return round(start_degrees * self._QT_ANGLE_UNIT)

    def _arc_direction(self, arc_degrees: Optional[float]) -> int:
        if arc_degrees is None:
            return 1

        return -1

    def _overlap_span_angle(self, track_span_angle: int) -> int:
        if track_span_angle <= 0:
            return 0

        overlap_span_angle = round(
            self.ARC_OVERLAP_DEGREES * self._QT_ANGLE_UNIT
        )
        return min(overlap_span_angle, track_span_angle // 2)

    def _resolved_track_color(
        self,
        palette: QPalette,
        *,
        selected: bool,
    ) -> QColor:
        if self._track_color is not None:
            return QColor(self._track_color)

        text_color = palette.color(QPalette.ColorRole.WindowText)
        window_color = palette.color(QPalette.ColorRole.Window)
        color = mix_colors(text_color, window_color, 0.70)
        color.setAlpha(round(color.alpha() * 0.70))

        return color

    def _resolved_arc_color(
        self,
        palette: QPalette,
        *,
        selected: bool,
    ) -> QColor:
        if self._arc_color is not None:
            return QColor(self._arc_color)

        return palette.color(QPalette.ColorRole.Highlight)
