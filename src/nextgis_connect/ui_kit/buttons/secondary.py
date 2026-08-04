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

from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.ui_kit.buttons.animated import (
    AnimatedButtonBase,
    ButtonVisualState,
)
from nextgis_connect.ui_kit.graphics.decorator import (
    NextgisDecorator,
)


class SecondaryButton(AnimatedButtonBase):
    """Show the secondary NextGIS action button.

    Use transparent and muted visual states while preserving the shared
    animated button behavior.
    """

    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the secondary button.

        :param text: Initial button text.
        :param parent: Parent widget.
        """
        super().__init__(text, parent)
        self.setFlat(True)

    def _normal_state(self) -> ButtonVisualState:
        text_color = NextgisDecorator.system_text_color(self._initial_palette)
        border_color = QColor(text_color)
        border_color.setAlphaF(0.20)
        transparent = QColor(0, 0, 0, 0)

        return ButtonVisualState(
            background=transparent,
            border=border_color,
            text=text_color,
        )

    def _hover_state(self) -> ButtonVisualState:
        color = NextgisDecorator.brand_hover_color()
        text_color = NextgisDecorator.system_text_color(self._initial_palette)

        return ButtonVisualState(
            background=NextgisDecorator.brand_overlay_color(0.05),
            border=color,
            text=text_color,
        )

    def _pressed_state(self) -> ButtonVisualState:
        color = NextgisDecorator.brand_active_color()
        text_color = NextgisDecorator.system_text_color(self._initial_palette)
        text_color = text_color.darker(120)

        return ButtonVisualState(
            background=NextgisDecorator.brand_overlay_color(0.12),
            border=color,
            text=text_color,
        )

    def _disabled_state(self) -> ButtonVisualState:
        helper_color = NextgisDecorator.system_muted_text_color(
            self._initial_palette
        )
        transparent = QColor(0, 0, 0, 0)

        return ButtonVisualState(
            background=transparent,
            border=helper_color,
            text=helper_color,
        )
