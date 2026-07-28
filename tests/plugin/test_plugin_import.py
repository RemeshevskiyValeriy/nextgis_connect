import importlib

import qgis.utils

import nextgis_connect
from nextgis_connect.shared.constants import PACKAGE_NAME


def test_plugin_package_imports(qgis_iface) -> None:
    del qgis_iface

    plugin_module = importlib.import_module("nextgis_connect.plugin")

    assert callable(nextgis_connect.classFactory)
    assert plugin_module.NgConnectPlugin is not None


def test_plugin_loads(qgis_iface) -> None:
    plugin = nextgis_connect.classFactory(qgis_iface)
    qgis.utils.plugins[PACKAGE_NAME] = plugin

    plugin._load()

    try:
        assert plugin.container is not None
    finally:
        plugin._unload()
        qgis.utils.plugins.pop(PACKAGE_NAME, None)
