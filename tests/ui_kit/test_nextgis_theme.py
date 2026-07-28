import json
from pathlib import Path

try:
    import tomllib
except ImportError:
    import pip._vendor.tomli as tomllib

from qgis.PyQt.QtGui import QColor, QPalette

from nextgis_connect.ui_kit.rendering.graphics.decorator import (
    NextgisBrandColor,
    NextgisDecorator,
    NextgisRadius,
    NextgisSize,
    NextgisSpacing,
    mix_colors,
)
from nextgis_connect.ui_kit.widgets.buttons.primary import PrimaryButton

ROOT = Path(__file__).resolve().parents[2]
THEME_PATH = (
    ROOT / "src" / "nextgis_connect" / "assets" / "themes" / "nextgis.json"
)


def _theme() -> dict:
    return json.loads(THEME_PATH.read_text(encoding="utf-8"))


def _color_name(value: str) -> str:
    return QColor(value).name()


def test_decorator_reads_brand_tokens_from_theme() -> None:
    theme = _theme()
    shared_colors = theme["color"]["shared"]

    assert NextgisDecorator.brand_color().name() == _color_name(
        shared_colors["brand"]
    )
    assert NextgisDecorator.brand_hover_color().name() == _color_name(
        shared_colors["brandHover"]
    )
    assert NextgisDecorator.brand_active_color().name() == _color_name(
        shared_colors["brandActive"]
    )
    assert NextgisDecorator.brand_color(NextgisBrandColor.ACCENT).name() == (
        _color_name(shared_colors["brandAccent"])
    )
    assert NextgisDecorator.brand_on_color().name() == _color_name(
        shared_colors["onBrand"]
    )


def test_decorator_exposes_system_palette_colors() -> None:
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#202124"))
    palette.setColor(QPalette.ColorRole.Base, QColor("#2a2b2f"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#f1f3f4"))
    palette.setColor(QPalette.ColorRole.Text, QColor("#e8eaed"))
    palette.setColor(QPalette.ColorRole.Mid, QColor("#5f6368"))

    assert NextgisDecorator.system_window_color(palette).name() == "#202124"
    assert NextgisDecorator.system_base_color(palette).name() == "#2a2b2f"
    assert NextgisDecorator.system_title_color(palette).name() == "#f1f3f4"
    assert NextgisDecorator.system_text_color(palette).name() == "#e8eaed"
    assert NextgisDecorator.system_border_color(palette).name() == "#5f6368"


def test_overlay_palette_uses_system_surface_colors() -> None:
    base_palette = QPalette()
    window_color = QColor("#101820")
    base_color = QColor("#182430")
    text_color = QColor("#e6edf3")
    mid_color = QColor("#52616f")
    base_palette.setColor(QPalette.ColorRole.Window, window_color)
    base_palette.setColor(QPalette.ColorRole.Base, base_color)
    base_palette.setColor(QPalette.ColorRole.WindowText, text_color)
    base_palette.setColor(QPalette.ColorRole.Text, text_color)
    base_palette.setColor(QPalette.ColorRole.Mid, mid_color)

    palette = NextgisDecorator.overlay_card_palette(base_palette)

    assert palette.color(QPalette.ColorRole.Window).name() == _color_name(
        mix_colors(window_color, base_color, 0.82).name()
    )
    assert palette.color(QPalette.ColorRole.WindowText).name() == _color_name(
        text_color.name()
    )
    assert palette.color(QPalette.ColorRole.Mid).name() == _color_name(
        mid_color.name()
    )


def test_primary_button_uses_theme_colors(qgis_app) -> None:
    del qgis_app

    theme = _theme()
    shared_colors = theme["color"]["shared"]

    button = PrimaryButton("Update")
    try:
        assert button.minimumHeight() == theme["sizePx"]["controlCompact"]
        assert button._border_radius() == theme["radiusPx"]["button"]
        assert button._horizontal_padding() == theme["spacingPx"]["4"]
        assert (
            NextgisDecorator.size(NextgisSize.CONTROL_COMPACT)
            == theme["sizePx"]["controlCompact"]
        )
        assert (
            NextgisDecorator.radius(NextgisRadius.BUTTON)
            == theme["radiusPx"]["button"]
        )
        assert (
            NextgisDecorator.spacing(NextgisSpacing.LG)
            == theme["spacingPx"]["4"]
        )
        assert button._normal_state().background.name() == _color_name(
            shared_colors["brand"]
        )
        assert button._hover_state().background.name() == _color_name(
            shared_colors["brandHover"]
        )
        assert button._pressed_state().background.name() == _color_name(
            shared_colors["brandActive"]
        )
    finally:
        button.deleteLater()


def test_theme_file_is_included_in_package_data() -> None:
    pyproject = tomllib.loads(
        (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    package_data = pyproject["tool"]["qgspb"]["package-data"]

    assert package_data["nextgis_connect.assets.themes"] == ["**/*.json"]
