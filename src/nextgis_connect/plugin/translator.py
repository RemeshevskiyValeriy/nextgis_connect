from pathlib import Path

from qgis.core import QgsApplication

from nextgis_connect.plugin.plugin_interface import NgConnectInterface


def initialize_translator(
    plugin: NgConnectInterface,
    plugin_dir: Path,
) -> None:
    application = QgsApplication.instance()
    assert application is not None
    locale = application.locale()
    plugin._add_translator(
        plugin_dir / "i18n" / f"nextgis_connect_{locale}.qm",
    )
