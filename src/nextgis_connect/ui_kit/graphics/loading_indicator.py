# NextGIS Toolbox
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

    _QT_ANGLE_UNIT = 16
    _ARC_START_DEGREES = 45.0

    def __init__(
        self,
        *,
        track_color: Optional[QColor] = None,
        arc_color: Optional[QColor] = None,
    ) -> None:
        """Initialize the loading indicator renderer.

        :param track_color: Optional track color override.
        :param arc_color: Optional arc color override.
        """
        self._track_color = (
            None if track_color is None else QColor(track_color)
        )
        self._arc_color = None if arc_color is None else QColor(arc_color)

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
        :param selected: Whether to use selected-state colors.
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
    ) -> None:
        """Paint the loading indicator.

        :param painter: Painter used for rendering.
        :param rect: Rectangle to paint into.
        :param angle: Arc rotation angle in degrees.
        :param palette: Palette used for default colors.
        :param selected: Whether to use selected-state colors.
        """
        if rect.width() <= 0 or rect.height() <= 0:
            return

        indicator_rect = self._indicator_rect(rect)
        if indicator_rect.width() <= 0 or indicator_rect.height() <= 0:
            return

        active_palette = NextgisDecorator.system_palette(palette)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        track_pen = QPen(
            self._resolved_track_color(active_palette, selected=selected),
            self.PEN_WIDTH,
        )
        track_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(indicator_rect)

        arc_pen = QPen(
            self._resolved_arc_color(active_palette, selected=selected),
            self.PEN_WIDTH,
        )
        arc_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(arc_pen)
        painter.drawArc(
            indicator_rect,
            self._arc_start_angle(angle),
            round(self.ARC_DEGREES * self._QT_ANGLE_UNIT),
        )

        painter.restore()

    def _normalize_size(self, size: Optional[QSize]) -> QSize:
        if size is None or not size.isValid() or size.isEmpty():
            return QSize(self.DEFAULT_SIZE)

        return QSize(size)

    def _indicator_rect(self, rect: QRectF) -> QRectF:
        side = max(0.0, min(rect.width(), rect.height()))
        left = rect.left() + (rect.width() - side) / 2.0
        top = rect.top() + (rect.height() - side) / 2.0

        indicator_rect = QRectF(left, top, side, side)
        inset = self.PEN_WIDTH / 2.0
        indicator_rect.adjust(inset, inset, -inset, -inset)

        return indicator_rect

    def _arc_start_angle(self, angle: float) -> int:
        normalized_angle = angle % 360.0
        start_degrees = self._ARC_START_DEGREES - normalized_angle

        return round(start_degrees * self._QT_ANGLE_UNIT)

    def _resolved_track_color(
        self,
        palette: QPalette,
        *,
        selected: bool,
    ) -> QColor:
        if self._track_color is not None:
            return QColor(self._track_color)

        if selected:
            text_color = palette.color(QPalette.ColorRole.HighlightedText)
            window_color = palette.color(QPalette.ColorRole.Highlight)
        else:
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

        if selected:
            return palette.color(QPalette.ColorRole.HighlightedText)

        return NextgisDecorator.brand_color()
