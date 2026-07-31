from typing import Dict, Optional

from qgis.PyQt.QtCore import QRect, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QImage, QPainter, QPalette, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer

from nextgis_connect.features.synchronization.presentation.attachments.attachment_display_state import (
    AttachmentDisplayState,
)
from nextgis_connect.ui_kit.graphics.loading_indicator import (
    LoadingIndicatorRenderer,
)
from nextgis_connect.ui_kit.icons import material_icon_path


class AttachmentIconPainter:
    """Paint attachment icons with cache and loading overlays."""

    DOWNLOAD_ICON_NAME = "download_for_offline"
    LOADING_DOWNLOAD_ICON_NAME = "download_for_offline_arrow"
    DOWNLOAD_ICON_MIN_SIZE = 28
    DISABLED_ICON_COLOR = QColor("#8c8c8c")
    DISABLED_ICON_BLEND = 0.72
    LOADING_INDICATOR_SOURCE_SIZE = 48.0
    LOADING_INDICATOR_SOURCE_INSET = 4.0
    LOADING_INDICATOR_SOURCE_PEN_WIDTH = 3.0
    LOADING_TRACK_COLOR = QColor(255, 255, 255, 150)
    UNCACHED_IMAGE_OVERLAY = QColor(0, 0, 0, 180)

    def __init__(
        self,
        thumbnail_size: QSize,
        *,
        loading_renderer: Optional[LoadingIndicatorRenderer] = None,
    ) -> None:
        self._thumbnail_size = QSize(thumbnail_size)
        self._loading_renderer = loading_renderer or LoadingIndicatorRenderer(
            track_color=self.LOADING_TRACK_COLOR
        )
        self._download_icon_renderers: Dict[str, QSvgRenderer] = {}

    def paint(
        self,
        painter: QPainter,
        rect: QRect,
        state: AttachmentDisplayState,
        *,
        palette: QPalette,
        selected: bool,
        loading_angle: float = 0.0,
        show_loading_progress: bool = True,
    ) -> None:
        """Paint the icon and the required overlays."""
        if state.is_loading and state.is_preview_loading:
            loading_progress = (
                state.loading_progress if show_loading_progress else None
            )
            self._paint_loading_background(painter, rect)
            self._paint_loading_overlay(
                painter,
                rect,
                loading_progress,
                palette=palette,
                selected=selected,
                angle=loading_angle,
            )
            return

        self._paint_base_icon(painter, rect, state)

        if state.is_loading:
            loading_progress = (
                state.loading_progress if show_loading_progress else None
            )
            self._paint_download_overlay(
                painter,
                rect,
                icon_name=self.LOADING_DOWNLOAD_ICON_NAME,
            )
            self._paint_loading_overlay(
                painter,
                rect,
                loading_progress,
                palette=palette,
                selected=selected,
                angle=loading_angle,
            )
            return

        if not state.is_cached:
            self._paint_download_overlay(painter, rect)

    def _paint_loading_background(
        self,
        painter: QPainter,
        rect: QRect,
    ) -> None:
        overlay_rect = self._overlay_rect(rect)

        painter.save()
        self._paint_overlay_background(painter, overlay_rect)
        painter.restore()

    def _paint_base_icon(
        self,
        painter: QPainter,
        rect: QRect,
        state: AttachmentDisplayState,
    ) -> None:
        icon_value = state.icon_value
        if isinstance(icon_value, QIcon):
            pixmap = icon_value.pixmap(self._thumbnail_size)
            if not state.is_cached:
                pixmap = self._disabled_pixmap(pixmap)
            self._draw_centered_pixmap(painter, rect, pixmap)
            return

        if isinstance(icon_value, QPixmap):
            pixmap = icon_value.scaled(
                self._thumbnail_size,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            if not state.is_cached:
                pixmap = self._dimmed_pixmap(pixmap)
            self._draw_centered_pixmap(painter, rect, pixmap)

    def _draw_centered_pixmap(
        self,
        painter: QPainter,
        rect: QRect,
        pixmap: QPixmap,
    ) -> None:
        if pixmap.isNull():
            return

        x = rect.x() + (rect.width() - pixmap.width()) // 2
        y = rect.y() + (rect.height() - pixmap.height()) // 2
        painter.drawPixmap(x, y, pixmap)

    def _disabled_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap

        device_pixel_ratio = pixmap.devicePixelRatio()
        image = pixmap.toImage().convertToFormat(QImage.Format.Format_ARGB32)
        for y in range(image.height()):
            for x in range(image.width()):
                color = image.pixelColor(x, y)
                if color.alpha() == 0:
                    continue

                disabled_color = self._disabled_color(color)
                image.setPixelColor(x, y, disabled_color)

        result = QPixmap.fromImage(image)
        result.setDevicePixelRatio(device_pixel_ratio)
        return result

    def _disabled_color(self, color: QColor) -> QColor:
        disabled_color = QColor(
            self._blended_channel(color.red(), self.DISABLED_ICON_COLOR.red()),
            self._blended_channel(
                color.green(),
                self.DISABLED_ICON_COLOR.green(),
            ),
            self._blended_channel(
                color.blue(),
                self.DISABLED_ICON_COLOR.blue(),
            ),
            color.alpha(),
        )
        return disabled_color

    def _blended_channel(self, source: int, target: int) -> int:
        return round(
            source * (1.0 - self.DISABLED_ICON_BLEND)
            + target * self.DISABLED_ICON_BLEND
        )

    def _dimmed_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap

        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.fillRect(result.rect(), self.UNCACHED_IMAGE_OVERLAY)
        painter.end()
        return result

    def _paint_download_overlay(
        self,
        painter: QPainter,
        rect: QRect,
        *,
        icon_name: str = DOWNLOAD_ICON_NAME,
    ) -> None:
        overlay_rect = self._overlay_rect(rect)

        painter.save()
        self._paint_overlay_background(painter, overlay_rect)
        self._paint_download_icon(
            painter,
            icon_name,
            QRectF(overlay_rect),
        )
        painter.restore()

    def _paint_overlay_background(
        self,
        painter: QPainter,
        overlay_rect: QRect,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(QColor(0, 0, 0, 120))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(overlay_rect)

    def _paint_download_icon(
        self,
        painter: QPainter,
        icon_name: str,
        rect: QRectF,
    ) -> None:
        self._download_icon_renderer(icon_name).render(painter, rect)

    def _download_icon_renderer(self, icon_name: str) -> QSvgRenderer:
        renderer = self._download_icon_renderers.get(icon_name)
        if renderer is not None:
            return renderer

        icon_path = material_icon_path(icon_name)
        if icon_path is None:
            message = f"SVG file not found: {icon_name}"
            raise FileNotFoundError(message)

        renderer = QSvgRenderer(str(icon_path))
        if not renderer.isValid():
            message = f"Failed to load SVG file: {icon_path}"
            raise ValueError(message)

        self._download_icon_renderers[icon_name] = renderer
        return renderer

    def _paint_loading_overlay(
        self,
        painter: QPainter,
        rect: QRect,
        progress: Optional[float],
        *,
        palette: QPalette,
        selected: bool,
        angle: float,
    ) -> None:
        overlay_rect = self._overlay_rect(rect)

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._loading_renderer.paint(
            painter,
            self._loading_indicator_rect(overlay_rect),
            angle=angle,
            palette=palette,
            selected=False,
            arc_degrees=self._arc_degrees(progress),
            pen_width=self._loading_indicator_pen_width(overlay_rect),
        )
        painter.restore()

    def _loading_indicator_rect(self, overlay_rect: QRect) -> QRectF:
        indicator_rect = QRectF(overlay_rect)
        inset = (
            self.LOADING_INDICATOR_SOURCE_INSET
            * self._loading_indicator_scale(overlay_rect)
        )
        indicator_rect.adjust(
            inset,
            inset,
            -inset,
            -inset,
        )
        return indicator_rect

    def _loading_indicator_pen_width(self, overlay_rect: QRect) -> float:
        return (
            self.LOADING_INDICATOR_SOURCE_PEN_WIDTH
            * self._loading_indicator_scale(overlay_rect)
        )

    def _loading_indicator_scale(self, overlay_rect: QRect) -> float:
        side = min(overlay_rect.width(), overlay_rect.height())
        return side / self.LOADING_INDICATOR_SOURCE_SIZE

    def _overlay_rect(self, rect: QRect) -> QRect:
        size = max(
            self.DOWNLOAD_ICON_MIN_SIZE,
            min(rect.width(), rect.height()) // 2,
        )
        overlay_rect = QRect(0, 0, size, size)
        overlay_rect.moveCenter(rect.center())
        return overlay_rect

    def _arc_degrees(self, progress: Optional[float]) -> Optional[float]:
        if progress is None:
            return None

        if progress <= 0:
            return 12.0

        return max(12.0, min(360.0, progress * 3.6))
