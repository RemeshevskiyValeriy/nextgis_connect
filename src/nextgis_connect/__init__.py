from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    from nextgis_connect.plugin.plugin_interface import NgConnectInterface


def classFactory(iface: "QgisInterface") -> "NgConnectInterface":
    from nextgis_connect.plugin.plugin_factory import create_plugin

    return create_plugin(iface)
