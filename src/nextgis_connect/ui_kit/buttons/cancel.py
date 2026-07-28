from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QRect, QRectF, QSize
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.ui_kit.buttons.animated import ButtonVisualState
from nextgis_connect.ui_kit.buttons.secondary import SecondaryButton
from nextgis_connect.ui_kit.graphics import CustomSvgRenderer


class CancelButton(SecondaryButton):
    _MATERIAL_ICONS_DIR = (
        Path(__file__).resolve().parents[3] / "assets" / "icons" / "material"
    )

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ) -> None:
        self._is_waiting = False
        self._icon_name = ""
        self._icon_renderer: Optional[CustomSvgRenderer] = None

        super().__init__("", parent)
        self.setToolTip(self.tr("Cancel"))
        self.set_button_height(self.minimumHeight())

    def set_waiting(self, is_waiting: bool) -> None:
        if self._is_waiting == is_waiting:
            return

        self._is_waiting = is_waiting
        self.setEnabled(not is_waiting)
        self._refresh_visual_state(animated=False)

    def is_waiting(self) -> bool:
        return self._is_waiting

    def set_button_height(self, height: int) -> None:
        super().set_button_height(height)
        self.setFixedWidth(height)
        self.setIconSize(QSize(max(16, height - 12), max(16, height - 12)))
        self._refresh_visual_state(animated=False)

    def _horizontal_padding(self) -> int:
        return 0

    def _content_width(self) -> int:
        return self.iconSize().width()

    def _paint_content(self, painter: QPainter, rect: QRect) -> None:
        del rect

        if self._icon_renderer is None or not self._icon_renderer.is_valid():
            return

        icon_size = self.iconSize()
        render_size = min(
            icon_size.width(),
            icon_size.height(),
            self.width(),
            self.height(),
        )
        icon_rect = QRectF(
            (self.width() - render_size) / 2,
            (self.height() - render_size) / 2,
            render_size,
            render_size,
        )
        self._icon_renderer.render(painter, icon_rect)

    def _after_visual_state_applied(self, state: ButtonVisualState) -> None:
        icon_name = (
            "hourglass"
            if getattr(self, "_is_waiting", False)
            else "close_small"
        )
        self._ensure_icon_renderer(icon_name)
        if self._icon_renderer is not None:
            self._icon_renderer.set_fill_color(state.text)

    def _ensure_icon_renderer(self, icon_name: str) -> None:
        if self._icon_name == icon_name:
            return

        icon_path = self._material_icon_path(icon_name)
        self._icon_renderer = (
            CustomSvgRenderer(icon_path, self)
            if icon_path is not None
            else None
        )
        self._icon_name = icon_name

    def _material_icon_path(self, icon_name: str) -> Optional[Path]:
        paths = sorted(self._MATERIAL_ICONS_DIR.glob(f"{icon_name}*.svg"))
        return paths[0] if paths else None
