from typing import List, Optional, Sequence, Tuple

from qgis.core import (
    QgsMapLayer,
    QgsMapLayerStyle,
    QgsMapLayerStyleManager,
)
from qgis.PyQt.QtXml import QDomDocument

from nextgis_connect.features.resource_browser.domain import (
    ResourceImportStyle,
)


class QgisResourceLayerStyleApplicator:
    """Install downloaded QGIS styles on a newly constructed layer."""

    _TEMPORARY_STYLE_PREFIX = "_NGW_DEFAULT"

    def apply(
        self,
        styles: Sequence[ResourceImportStyle],
        layer: QgsMapLayer,
        default_style_name: Optional[str] = None,
    ) -> bool:
        """Replace the provider style and select the detached-style default."""
        if len(styles) == 0:
            return False

        prepared_styles = self._prepare_styles(styles)
        style_manager = layer.styleManager()
        if style_manager is None:
            raise RuntimeError("The QGIS layer has no style manager")

        style_names = [name for name, _ in prepared_styles]
        self._validate_names(style_names, style_manager.styles())

        original_style_name = style_manager.currentStyle()
        temporary_style_name = self._temporary_style_name(
            style_manager.styles(),
            style_names,
        )
        if not style_manager.renameStyle(
            original_style_name,
            temporary_style_name,
        ):
            raise RuntimeError("Could not preserve the provider style")

        added_style_names: List[str] = []
        try:
            for style_name, qgis_style in prepared_styles:
                if not style_manager.addStyle(style_name, qgis_style):
                    raise RuntimeError(
                        f'Could not add QGIS style "{style_name}"'
                    )
                added_style_names.append(style_name)

            selected_style_name = self._selected_style_name(
                style_names,
                layer.name(),
                default_style_name,
            )
            if not style_manager.setCurrentStyle(selected_style_name):
                raise RuntimeError(
                    f'Could not select QGIS style "{selected_style_name}"'
                )
            if not style_manager.removeStyle(temporary_style_name):
                raise RuntimeError("Could not remove the provider style")
        except Exception:
            self._restore_provider_style(
                style_manager,
                original_style_name,
                temporary_style_name,
                added_style_names,
            )
            raise

        return True

    def _selected_style_name(
        self,
        style_names: Sequence[str],
        layer_name: str,
        default_style_name: Optional[str],
    ) -> str:
        if default_style_name is not None:
            if default_style_name not in style_names:
                raise RuntimeError(
                    f'QGIS style "{default_style_name}" is unavailable'
                )
            return default_style_name

        return layer_name if layer_name in style_names else style_names[0]

    def _prepare_styles(
        self,
        styles: Sequence[ResourceImportStyle],
    ) -> Tuple[Tuple[str, QgsMapLayerStyle], ...]:
        prepared_styles = []
        for style in sorted(styles, key=lambda item: item.name):
            qgis_style = QgsMapLayerStyle(style.qml)
            if not qgis_style.isValid() or not self._is_qml_valid(style.qml):
                raise RuntimeError(f'QGIS style "{style.name}" is not valid')
            prepared_styles.append((style.name, qgis_style))

        return tuple(prepared_styles)

    def _is_qml_valid(self, qml: str) -> bool:
        document = QDomDocument()
        parse_result = document.setContent(qml)
        is_valid = (
            parse_result[0]
            if isinstance(parse_result, tuple)
            else parse_result
        )
        return (
            bool(is_valid) and document.documentElement().tagName() == "qgis"
        )

    def _validate_names(
        self,
        style_names: Sequence[str],
        existing_style_names: Sequence[str],
    ) -> None:
        if len(set(style_names)) != len(style_names):
            raise RuntimeError("QGIS style names must be unique")

        current_style_names = set(existing_style_names)
        if len(current_style_names) > 1:
            collisions = current_style_names.intersection(style_names)
            if len(collisions) > 0:
                names = ", ".join(sorted(collisions))
                raise RuntimeError(f"QGIS styles already exist: {names}")

    def _temporary_style_name(
        self,
        existing_style_names: Sequence[str],
        added_style_names: Sequence[str],
    ) -> str:
        unavailable_names = set(existing_style_names).union(added_style_names)
        temporary_style_name = self._TEMPORARY_STYLE_PREFIX
        suffix = 1
        while temporary_style_name in unavailable_names:
            temporary_style_name = f"{self._TEMPORARY_STYLE_PREFIX}_{suffix}"
            suffix += 1
        return temporary_style_name

    def _restore_provider_style(
        self,
        style_manager: QgsMapLayerStyleManager,
        original_style_name: str,
        temporary_style_name: str,
        added_style_names: Sequence[str],
    ) -> None:
        for style_name in reversed(added_style_names):
            style_manager.removeStyle(style_name)

        if temporary_style_name not in style_manager.styles():
            return

        style_manager.renameStyle(
            temporary_style_name,
            original_style_name,
        )
        style_manager.setCurrentStyle(original_style_name)
