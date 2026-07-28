from pathlib import Path

from qgis.PyQt.QtGui import QColor, QPalette

from nextgis_connect.legacy.tree_widget.overlay.widgets.surface import (
    LogoLinkWidget,
)

ROOT = Path(__file__).resolve().parents[2]
LOGO_PATH = (
    ROOT
    / "src"
    / "nextgis_connect"
    / "assets"
    / "icons"
    / "branding"
    / "nextgis_full_logo.svg"
)


def _svg_text(widget: LogoLinkWidget, renderer_name: str) -> str:
    renderer = getattr(widget, renderer_name)
    return bytes(renderer.themed_data()).decode("utf-8").lower()


def test_logo_hover_layer_preserves_brand_color(qgis_app) -> None:
    del qgis_app

    widget = LogoLinkWidget(LOGO_PATH)
    try:
        palette = QPalette(widget.palette())
        palette.setColor(QPalette.ColorRole.Text, QColor("#123456"))
        widget.setPalette(palette)
        widget._sync_logo_renderers()

        monochrome_svg = _svg_text(widget, "_monochrome_renderer")
        color_svg = _svg_text(widget, "_color_renderer")

        assert "#123456" in monochrome_svg
        assert "#176fc1" not in monochrome_svg
        assert "#123456" in color_svg
        assert "#176fc1" in color_svg
    finally:
        widget.deleteLater()
