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
from unittest.mock import patch

import qgis.utils
from qgis.utils import updateAvailablePlugins

import nextgis_connect
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.legacy.settings.ng_connect_settings import (
    NgConnectSettings,
)
from nextgis_connect.platform.qgis.compat import parse_version
from nextgis_connect.shared.constants import PACKAGE_NAME
from tests.ng_connect_testcase import NgConnectTestCase, TestConnection


class TestNgConnectPlugin(NgConnectTestCase):
    def test_plugin_deprecation(self) -> None:
        settings = NgConnectSettings()
        supported_version_for_connect = parse_version(
            settings.supported_ngw_version
        )

        connection_id = self.connection_id(TestConnection.DemoGuest)
        connection = QgsNgwConnection(connection_id)
        version_response = {
            "nextgisweb": (
                f"{supported_version_for_connect.major}."
                f"{supported_version_for_connect.minor}.0"
            )
        }
        with patch.object(
            QgsNgwConnection,
            "get",
            return_value=version_response,
        ) as get:
            data = connection.get("api/component/pyramid/pkg_version")

        get.assert_called_once_with("api/component/pyramid/pkg_version")
        ngw_version = parse_version(data["nextgisweb"])

        self.assertTrue(
            supported_version_for_connect.major == ngw_version.major
            and supported_version_for_connect.minor == ngw_version.minor
        )

    def test_plugin_creation(self) -> None:
        nextgis_connect_path = Path(nextgis_connect.__file__).parents[1]
        qgis.utils.plugin_paths.append(str(nextgis_connect_path))
        updateAvailablePlugins()
        qgis.utils.plugins[PACKAGE_NAME] = nextgis_connect.classFactory(
            qgis.utils.iface  # pyright: ignore[reportArgumentType]
        )
