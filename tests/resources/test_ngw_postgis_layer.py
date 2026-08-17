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

from unittest import mock

from qgis.core import QgsDataSourceUri

from nextgis_connect.legacy.ngw.core.ngw_postgis_layer import (
    DEFAULT_POSTGRES_PORT,
    NGWPostgisConnection,
    NGWPostgisLayer,
)


def test_layer_params_uses_default_port_for_null_port() -> None:
    postgis_connection = NGWPostgisConnection(
        mock.Mock(),
        {
            "resource": {
                "id": 1,
                "cls": "postgis_connection",
                "display_name": "connection",
                "parent": None,
                "children": False,
                "owner_user": None,
            },
            "postgis_connection": {
                "hostname": "database.example.com",
                "port": None,
                "database": "gis",
                "username": "alice",
                "password": "secret",
            },
        },
    )
    postgis_layer = NGWPostgisLayer(
        mock.Mock(),
        {
            "resource": {
                "id": 2,
                "cls": "postgis_layer",
                "display_name": "roads",
                "parent": None,
                "children": False,
                "owner_user": None,
            },
            "postgis_layer": {
                "connection": {"id": 1},
                "schema": "public",
                "table": "roads",
                "column_geom": "geom",
                "column_id": "id",
            },
        },
    )

    uri_string, layer_name, provider = postgis_layer.layer_params(
        postgis_connection
    )
    uri = QgsDataSourceUri(uri_string)

    assert uri.host() == "database.example.com"
    assert uri.port() == str(DEFAULT_POSTGRES_PORT)
    assert uri.database() == "gis"
    assert layer_name == "roads"
    assert provider == "postgres"
