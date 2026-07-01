from enum import Enum
from typing import Iterable, Mapping, Optional, Tuple, Union

from qgis.core import QgsApplication
from qgis.PyQt.QtGui import QColor, QPalette
from qgis.PyQt.QtWidgets import QWidget


class NextgisColor(Enum):
    MAIN = "#0c65af"
    PRESSED = "#0952a3"


PaletteKey = Union[
    QPalette.ColorRole,
    Tuple[QPalette.ColorGroup, QPalette.ColorRole],
]


def mix_colors(
    first_color: QColor,
    second_color: QColor,
    factor: float,
) -> QColor:
    clamped_factor = max(0.0, min(1.0, factor))
    inverse_factor = 1.0 - clamped_factor

    return QColor(
        round(
            first_color.red() * inverse_factor
            + second_color.red() * clamped_factor
        ),
        round(
            first_color.green() * inverse_factor
            + second_color.green() * clamped_factor
        ),
        round(
            first_color.blue() * inverse_factor
            + second_color.blue() * clamped_factor
        ),
        round(
            first_color.alpha() * inverse_factor
            + second_color.alpha() * clamped_factor
        ),
    )


class NextgisDecorator:
    DEFAULT_BUTTON_HEIGHT = 32
    CARD_MARGIN = 28
    CARD_PADDING_HORIZONTAL = 28
    CARD_PADDING_VERTICAL = 24
    CARD_SPACING = 12
    CARD_BUTTON_SPACING = 10
    CARD_MAX_WIDTH = 540
    CARD_MIN_WIDTH = 320
    GRID_SIZE = 40

    _COLOR_GROUPS = (
        QPalette.ColorGroup.Active,
        QPalette.ColorGroup.Inactive,
        QPalette.ColorGroup.Disabled,
    )

    @classmethod
    def application_palette(cls) -> QPalette:
        return QPalette(QgsApplication.palette())

    @classmethod
    def corporate_color(cls, color: NextgisColor) -> QColor:
        return QColor(color.value)

    @classmethod
    def is_dark_theme(cls, palette: Optional[QPalette] = None) -> bool:
        active_palette = QPalette(palette or cls.application_palette())
        window_color = active_palette.color(QPalette.ColorRole.Window)
        text_color = active_palette.color(QPalette.ColorRole.WindowText)

        return window_color.lightnessF() < text_color.lightnessF()

    @classmethod
    def title_color(cls, palette: Optional[QPalette] = None) -> QColor:
        active_palette = QPalette(palette or cls.application_palette())

        return active_palette.color(QPalette.ColorRole.WindowText)

    @classmethod
    def text_color(cls, palette: Optional[QPalette] = None) -> QColor:
        active_palette = QPalette(palette or cls.application_palette())

        return active_palette.color(QPalette.ColorRole.Text)

    @classmethod
    def helper_text_color(cls, palette: Optional[QPalette] = None) -> QColor:
        active_palette = QPalette(palette or cls.application_palette())
        text_color = active_palette.color(QPalette.ColorRole.Text)
        window_color = active_palette.color(QPalette.ColorRole.Window)
        factor = 0.45 if cls.is_dark_theme(active_palette) else 0.60

        return mix_colors(text_color, window_color, factor)

    @classmethod
    def accent_overlay_color(
        cls,
        alpha_factor: float = 0.05,
    ) -> QColor:
        color = cls.corporate_color(NextgisColor.MAIN)
        color.setAlpha(round(255 * max(0.0, min(1.0, alpha_factor))))

        return color

    @classmethod
    def accent_hover_color(cls, palette: Optional[QPalette] = None) -> QColor:
        active_palette = QPalette(palette or cls.application_palette())

        return mix_colors(
            cls.corporate_color(NextgisColor.MAIN),
            active_palette.color(QPalette.ColorRole.Base),
            0.16,
        )

    @classmethod
    def accent_pressed_color(cls) -> QColor:
        return cls.corporate_color(NextgisColor.PRESSED)

    @classmethod
    def accent_text_color(cls) -> QColor:
        return QColor("#ffffff")

    @classmethod
    def border_color(cls, palette: Optional[QPalette] = None) -> QColor:
        active_palette = QPalette(palette or cls.application_palette())

        return active_palette.color(QPalette.ColorRole.Mid)

    @classmethod
    def create_palette(
        cls,
        overrides: Mapping[PaletteKey, QColor],
        *,
        base_palette: Optional[QPalette] = None,
    ) -> QPalette:
        palette = QPalette(base_palette or cls.application_palette())

        for key, color in overrides.items():
            normalized_color = QColor(color)
            if isinstance(key, tuple):
                color_group, color_role = key
                palette.setColor(color_group, color_role, normalized_color)
                continue

            for color_group in cls._COLOR_GROUPS:
                palette.setColor(color_group, key, normalized_color)

        return palette

    @classmethod
    def overlay_card_palette(
        cls,
        palette: Optional[QPalette] = None,
    ) -> QPalette:
        active_palette = QPalette(palette or cls.application_palette())
        base_color = active_palette.color(QPalette.ColorRole.Base)
        window_color = active_palette.color(QPalette.ColorRole.Window)
        title_color = cls.title_color(active_palette)
        helper_color = cls.helper_text_color(active_palette)
        card_color = mix_colors(window_color, base_color, 0.82)
        disabled_text = mix_colors(title_color, card_color, 0.60)

        return cls.create_palette(
            {
                QPalette.ColorRole.Window: card_color,
                QPalette.ColorRole.Base: card_color,
                QPalette.ColorRole.WindowText: title_color,
                QPalette.ColorRole.Text: title_color,
                QPalette.ColorRole.Mid: cls.border_color(active_palette),
                (
                    QPalette.ColorGroup.Disabled,
                    QPalette.ColorRole.WindowText,
                ): disabled_text,
                (
                    QPalette.ColorGroup.Disabled,
                    QPalette.ColorRole.Text,
                ): helper_color,
            },
            base_palette=active_palette,
        )

    @classmethod
    def progress_palette(
        cls,
        palette: Optional[QPalette] = None,
    ) -> QPalette:
        active_palette = QPalette(palette or cls.application_palette())

        return cls.create_palette(
            {
                QPalette.ColorRole.Highlight: cls.corporate_color(
                    NextgisColor.MAIN
                ),
                QPalette.ColorRole.HighlightedText: cls.accent_text_color(),
            },
            base_palette=active_palette,
        )

    @classmethod
    def stylesheet(
        cls,
        selector: str,
        declarations: Mapping[str, str],
    ) -> str:
        rules = [
            f"{property_name}: {value};"
            for property_name, value in declarations.items()
        ]

        return f"{selector} {{ {''.join(rules)} }}"

    @classmethod
    def merge_stylesheets(cls, *stylesheets: str) -> str:
        return "\n".join(
            stylesheet
            for stylesheet in stylesheets
            if stylesheet.strip() != ""
        )

    @classmethod
    def patch_widget(
        cls,
        widget: QWidget,
        *,
        palette: Optional[QPalette] = None,
        stylesheets: Iterable[str] = (),
        auto_fill_background: Optional[bool] = None,
    ) -> None:
        if palette is not None:
            widget.setPalette(QPalette(palette))

        if auto_fill_background is not None:
            widget.setAutoFillBackground(auto_fill_background)

        merged_stylesheet = cls.merge_stylesheets(*stylesheets)
        if merged_stylesheet != widget.styleSheet():
            widget.setStyleSheet(merged_stylesheet)

    @classmethod
    def as_rgba(cls, color: QColor) -> str:
        return (
            f"rgba({color.red()}, {color.green()}, {color.blue()}, "
            f"{color.alphaF():.3f})"
        )


NEXTGIS_MAIN_COLOR = NextgisDecorator.corporate_color(NextgisColor.MAIN)
NEXTGIS_PRESSED_COLOR = NextgisDecorator.corporate_color(NextgisColor.PRESSED)
