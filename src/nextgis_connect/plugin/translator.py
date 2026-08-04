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

from pathlib import Path

from qgis.core import QgsApplication

from nextgis_connect.plugin.plugin_interface import NgConnectInterface


def initialize_translator(
    plugin: NgConnectInterface,
    plugin_dir: Path,
) -> None:
    """Initialize plugin translation resources.

    :param plugin: Plugin interface that owns translators.
    :param plugin_dir: Plugin installation directory.
    """
    application = QgsApplication.instance()
    assert application is not None
    locale = application.locale()
    plugin._add_translator(
        plugin_dir / "i18n" / f"nextgis_connect_{locale}.qm",
    )
