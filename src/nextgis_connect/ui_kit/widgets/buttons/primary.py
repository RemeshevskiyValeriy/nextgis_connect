from typing import Optional

from qgis.PyQt.QtGui import QPalette
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.ui_kit.rendering.graphics.decorator import (
    NextgisColor,
    NextgisDecorator,
    mix_colors,
)
from nextgis_connect.ui_kit.widgets.buttons.animated import (
    AnimatedButtonBase,
    ButtonVisualState,
)


class PrimaryButton(AnimatedButtonBase):
    def __init__(
        self,
        text: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(text, parent)

    def _normal_state(self) -> ButtonVisualState:
        color = NextgisDecorator.corporate_color(NextgisColor.MAIN)

        return ButtonVisualState(
            background=color,
            border=color,
            text=NextgisDecorator.accent_text_color(),
        )

    def _hover_state(self) -> ButtonVisualState:
        palette = QPalette(self.palette())
        hover_color = mix_colors(
            NextgisDecorator.corporate_color(NextgisColor.MAIN),
            palette.color(QPalette.ColorRole.Base),
            0.14,
        )

        return ButtonVisualState(
            background=hover_color,
            border=hover_color,
            text=NextgisDecorator.accent_text_color(),
        )

    def _pressed_state(self) -> ButtonVisualState:
        color = NextgisDecorator.corporate_color(NextgisColor.PRESSED)

        return ButtonVisualState(
            background=color,
            border=color,
            text=NextgisDecorator.accent_text_color(),
        )

    def _disabled_state(self) -> ButtonVisualState:
        palette = QPalette(self.palette())
        base_color = palette.color(QPalette.ColorRole.Button)
        disabled_color = mix_colors(
            NextgisDecorator.corporate_color(NextgisColor.MAIN),
            base_color,
            0.50,
        )
        text_color = mix_colors(
            NextgisDecorator.accent_text_color(),
            disabled_color,
            0.40,
        )

        return ButtonVisualState(
            background=disabled_color,
            border=disabled_color,
            text=text_color,
        )
