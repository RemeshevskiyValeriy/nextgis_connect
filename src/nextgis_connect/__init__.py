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
