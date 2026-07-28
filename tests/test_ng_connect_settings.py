from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QSettings

from nextgis_connect.legacy.settings.ng_connect_settings import (
    NgConnectSettings,
)
from nextgis_connect.shared.constants import PLUGIN_SETTINGS_GROUP


def test_migration_removes_obsolete_uploading_settings(
    reset_qgis_settings: None,
) -> None:
    del reset_qgis_settings

    _reset_settings_migration()

    qgs_settings = QgsSettings()
    old_settings = QSettings("NextGIS", "NextGIS WEB API")
    old_settings.clear()

    obsolete_qgs_keys = [
        "synchronization/period",
        "uploading/rasterAsCog",
        "uploading/vectorWithVersioning",
        "uploading/renameForbiddenFields",
    ]
    obsolete_old_keys = [
        "upload_cog_rasters",
        "upload_vector_with_versioning",
    ]

    for key in obsolete_qgs_keys:
        qgs_settings.setValue(f"{PLUGIN_SETTINGS_GROUP}/{key}", True)

    for key in obsolete_old_keys:
        old_settings.setValue(key, True)

    try:
        NgConnectSettings()

        for key in obsolete_qgs_keys:
            assert qgs_settings.value(f"{PLUGIN_SETTINGS_GROUP}/{key}") is None

        for key in obsolete_old_keys:
            assert old_settings.value(key) is None
    finally:
        old_settings.clear()
        _reset_settings_migration()


def _reset_settings_migration() -> None:
    NgConnectSettings._NgConnectSettings__is_migrated = False
