import copy

from qgis.core import QgsRuntimeProfiler
from qgis.gui import QgisInterface

from nextgis_connect.bootstrap.plugin_interface import NgConnectInterface
from nextgis_connect.platform.qgis.errors import (
    NgConnectReloadAfterUpdateWarning,
)
from nextgis_connect.settings.ng_connect_settings import NgConnectSettings


def create_plugin(iface: QgisInterface) -> NgConnectInterface:
    settings = NgConnectSettings()

    try:
        with QgsRuntimeProfiler.profile("Import plugin"):  # type: ignore
            from nextgis_connect.plugin import NgConnectPlugin

        plugin = NgConnectPlugin(iface)
        plugin.bootstrap()

        settings.did_last_launch_fail = False

    except Exception as error:
        from nextgis_connect.bootstrap.startup_stub import NgConnectPluginStub

        error_copy = copy.deepcopy(error)
        exception = error_copy

        if not settings.did_last_launch_fail and isinstance(
            error, ImportError
        ):
            exception = NgConnectReloadAfterUpdateWarning()
            exception.__cause__ = error_copy

        settings.did_last_launch_fail = True

        plugin = NgConnectPluginStub(startup_error=exception)

    return plugin
