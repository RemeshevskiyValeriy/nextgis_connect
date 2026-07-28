from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from qgis.gui import QgisInterface

    from nextgis_connect.plugin.plugin_interface import NgConnectInterface


def classFactory(iface: "QgisInterface") -> "NgConnectInterface":
    """Create the plugin instance for QGIS.

    :param iface: QGIS interface supplied by the plugin host.
    :return: Plugin interface instance.
    """
    from nextgis_connect.plugin.plugin_factory import create_plugin

    return create_plugin(iface)
