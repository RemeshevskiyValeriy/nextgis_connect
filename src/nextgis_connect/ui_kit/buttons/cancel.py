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

from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QRect, QRectF, QSize
from qgis.PyQt.QtGui import QPainter
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.ui_kit.buttons.animated import ButtonVisualState
from nextgis_connect.ui_kit.buttons.secondary import SecondaryButton
from nextgis_connect.ui_kit.graphics import CustomSvgRenderer
from nextgis_connect.ui_kit.icons import material_icon_path


class CancelButton(SecondaryButton):
    """Show a compact cancel button.

    Render a square secondary button that switches from a cancel icon
    to a waiting indicator icon when cancellation is already requested.
    """

    def __init__(
        self,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the cancel button.

        :param parent: Parent widget.
        """
        self._is_waiting = False
        self._icon_name = ""
        self._icon_renderer: Optional[CustomSvgRenderer] = None

        super().__init__("", parent)
        self.setToolTip(self.tr("Cancel"))
        self.set_button_height(self.minimumHeight())

    def set_waiting(self, is_waiting: bool) -> None:
        """Set whether the button is waiting.

        :param is_waiting: Whether cancellation is waiting for completion.
        """
        if self._is_waiting == is_waiting:
            return

        self._is_waiting = is_waiting
        self.setEnabled(not is_waiting)
        self._refresh_visual_state(animated=False)

    def is_waiting(self) -> bool:
        """Return whether the button is waiting.

        :return: ``True`` when the button is waiting.
        """
        return self._is_waiting

    def set_button_height(self, height: int) -> None:
        """Set the square button size.

        :param height: Button height and width in pixels.
        """
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
        return material_icon_path(icon_name)
