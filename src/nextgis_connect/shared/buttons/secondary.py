from typing import Optional

from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.shared.buttons.animated import (
    AnimatedButtonBase,
    ButtonVisualState,
)
from nextgis_connect.shared.graphics.decorator import (
    NextgisColor,
    NextgisDecorator,
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
        text_color = NextgisDecorator.text_color(self._initial_palette)
        border_color = QColor(text_color)
        border_color.setAlphaF(0.20)
        transparent = QColor(0, 0, 0, 0)

        return ButtonVisualState(
            background=transparent,
            border=border_color,
            text=text_color,
        )

    def _hover_state(self) -> ButtonVisualState:
        color = NextgisDecorator.corporate_color(NextgisColor.MAIN)
        text_color = NextgisDecorator.text_color(self._initial_palette)

        return ButtonVisualState(
            background=NextgisDecorator.accent_overlay_color(0.05),
            border=color,
            text=text_color,
        )

    def _pressed_state(self) -> ButtonVisualState:
        color = NextgisDecorator.corporate_color(NextgisColor.PRESSED)
        text_color = NextgisDecorator.text_color(self._initial_palette)
        text_color = text_color.darker(120)

        return ButtonVisualState(
            background=NextgisDecorator.accent_overlay_color(0.12),
            border=color,
            text=text_color,
        )

    def _disabled_state(self) -> ButtonVisualState:
        helper_color = NextgisDecorator.helper_text_color(
            self._initial_palette
        )
        transparent = QColor(0, 0, 0, 0)

        return ButtonVisualState(
            background=transparent,
            border=helper_color,
            text=helper_color,
        )
