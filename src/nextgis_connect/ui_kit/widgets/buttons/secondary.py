from typing import Optional

from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.ui_kit.rendering.graphics.decorator import (
    NextgisDecorator,
)
from nextgis_connect.ui_kit.widgets.buttons.animated import (
    AnimatedButtonBase,
    ButtonVisualState,
)


class SecondaryButton(AnimatedButtonBase):
    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
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
