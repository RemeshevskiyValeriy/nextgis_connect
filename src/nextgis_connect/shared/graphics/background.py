from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QObject, QRect, QRectF
from qgis.PyQt.QtGui import QColor, QLinearGradient, QPainter, QPalette, QPen

from nextgis_connect.shared.graphics.decorator import (
    NextgisColor,
    NextgisDecorator,
    mix_colors,
)
from nextgis_connect.shared.graphics.svg_renderer import CustomSvgRenderer


class NextgisBackgroundPainter(QObject):
    def __init__(
        self,
        isolines_path: Path,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._isolines_renderer = CustomSvgRenderer(
            isolines_path,
            self,
            themed=True,
        )

    def paint_widget_background(
        self,
        painter: QPainter,
        rect: QRect,
        *,
        palette: Optional[QPalette] = None,
    ) -> None:
        active_palette = QPalette(
            palette or NextgisDecorator.application_palette()
        )

        self._draw_grid(painter, rect, active_palette)
        self._draw_isolines(painter, rect, opacity=0.50)
        self._draw_vertical_gradient(painter, rect, active_palette)

    def paint_header_background(
        self,
        painter: QPainter,
        rect: QRect,
        *,
        palette: Optional[QPalette] = None,
    ) -> None:
        active_palette = QPalette(
            palette or NextgisDecorator.application_palette()
        )

        painter.save()
        painter.setClipRect(rect)
        self._draw_grid(painter, rect, active_palette)
        self._draw_isolines(painter, rect, opacity=0.25)
        self._draw_header_gradient(painter, rect, active_palette)
        painter.restore()

    def _draw_grid(
        self,
        painter: QPainter,
        rect: QRect,
        palette: QPalette,
    ) -> None:
        color = palette.color(QPalette.ColorRole.Text)
        color.setAlpha(50)

        pen = QPen(color)
        pen.setWidthF(0.5)
        painter.setPen(pen)

        grid_size = NextgisDecorator.GRID_SIZE
        x_coord = rect.left() - (rect.left() % grid_size)
        y_coord = rect.top() - (rect.top() % grid_size)

        while x_coord < rect.right() + grid_size:
            shifted_x = x_coord + grid_size // 2
            painter.drawLine(shifted_x, rect.top(), shifted_x, rect.bottom())
            x_coord += grid_size

        while y_coord < rect.bottom() + grid_size:
            shifted_y = y_coord + grid_size // 2
            painter.drawLine(rect.left(), shifted_y, rect.right(), shifted_y)
            y_coord += grid_size

    def _draw_isolines(
        self,
        painter: QPainter,
        rect: QRect,
        *,
        opacity: float,
    ) -> None:
        isolines_size = self._isolines_renderer.default_size()
        isolines_height = isolines_size.height()
        isolines_width = isolines_size.width()

        isolines_rect = QRectF(
            rect.left() + (rect.width() - isolines_width) / 2,
            rect.top() + (rect.height() - isolines_height) / 2,
            isolines_width,
            isolines_height,
        )

        painter.save()
        painter.setOpacity(opacity)
        self._isolines_renderer.render(painter, isolines_rect)
        painter.restore()

    def _draw_vertical_gradient(
        self,
        painter: QPainter,
        rect: QRect,
        palette: QPalette,
    ) -> None:
        background_color = palette.color(QPalette.ColorRole.Window)
        surface_color = palette.color(QPalette.ColorRole.Base)
        top_color = mix_colors(background_color, surface_color, 0.75)

        transparent_color = QColor(top_color)
        transparent_color.setAlpha(0)
        semi_transparent_color = QColor(top_color)
        semi_transparent_color.setAlpha(128)

        gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
        gradient.setColorAt(0.0, transparent_color)
        gradient.setColorAt(0.2, semi_transparent_color)
        gradient.setColorAt(1.0, top_color)
        painter.fillRect(rect, gradient)

    def _draw_header_gradient(
        self,
        painter: QPainter,
        rect: QRect,
        palette: QPalette,
    ) -> None:
        base_color = palette.color(QPalette.ColorRole.Base)
        window_color = palette.color(QPalette.ColorRole.Window)
        accent_color = mix_colors(
            base_color,
            NextgisDecorator.corporate_color(NextgisColor.MAIN),
            0.16,
        )
        bottom_color = mix_colors(window_color, base_color, 0.90)

        highlight_color = QColor(accent_color)
        highlight_color.setAlpha(210)
        bottom_color.setAlpha(150)

        gradient = QLinearGradient(
            rect.left(),
            rect.top(),
            rect.right(),
            rect.bottom(),
        )
        gradient.setColorAt(0.0, highlight_color)
        gradient.setColorAt(1.0, bottom_color)
        painter.fillRect(rect, gradient)
