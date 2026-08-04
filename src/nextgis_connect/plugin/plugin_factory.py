# NextGIS Connect
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

import copy

from qgis.core import QgsRuntimeProfiler
from qgis.gui import QgisInterface

from nextgis_connect.legacy.settings.ng_connect_settings import (
    NgConnectSettings,
)
from nextgis_connect.platform.qgis.errors import (
    NgConnectReloadAfterUpdateWarning,
)
from nextgis_connect.plugin.plugin_interface import NgConnectInterface


def create_plugin(iface: QgisInterface) -> NgConnectInterface:
    """Create the plugin interface for QGIS.

    :param iface: QGIS interface supplied by the plugin host.
    :return: Plugin interface instance.
    """
    settings = NgConnectSettings()

    try:
        with QgsRuntimeProfiler.profile("Import plugin"):  # type: ignore
            from nextgis_connect.plugin.plugin import NgConnectPlugin

        plugin = NgConnectPlugin(iface)
        plugin.initialize()

        settings.did_last_launch_fail = False

    except Exception as error:
        from nextgis_connect.plugin.startup_stub import NgConnectPluginStub

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
