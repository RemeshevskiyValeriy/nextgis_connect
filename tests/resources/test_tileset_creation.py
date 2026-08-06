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

from qgis.core import QgsProviderRegistry

from nextgis_connect.legacy.ngw.core import ngw_tileset
from nextgis_connect.legacy.ngw.core.ngw_resource_creator import (
    ResourceCreator,
)
from nextgis_connect.legacy.ngw.core.ngw_tileset import NGWTileset


def test_create_tileset_sends_tileset_payload(qgis_app) -> None:
    del qgis_app

    connection = mock.Mock()
    connection.tus_upload_file.return_value = {"id": "upload"}
    connection.post.return_value = {"id": 99}

    parent_resource = mock.Mock()
    parent_resource.resource_id = 42
    parent_resource.res_factory.connection = connection
    parent_resource.get_api_collection_url.return_value = "/api/resource/"

    upload_callback = mock.Mock()
    create_callback = mock.Mock()
    received_resource = mock.Mock()
    created_tileset = mock.Mock()

    with mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator.NGWResource"
        ".receive_resource_obj",
        return_value=received_resource,
    ) as receive_resource, mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator.NGWTileset",
        return_value=created_tileset,
    ) as tileset_constructor:
        tileset_constructor.type_id = "tileset"
        result = ResourceCreator.create_tileset(
            parent_resource,
            "/tmp/tiles.mbtiles",
            "Tiles",
            upload_callback,
            create_callback,
            metadata={
                "created_by": "NextGIS Connect/4.0.0",
                "source": "/tmp/tiles.mbtiles",
            },
        )

    assert result == created_tileset
    connection.tus_upload_file.assert_called_once_with(
        "/tmp/tiles.mbtiles",
        upload_callback,
        feedback=None,
    )
    create_callback.assert_called_once_with()
    connection.post.assert_called_once_with(
        "/api/resource/",
        params={
            "resource": {
                "cls": "tileset",
                "parent": {"id": 42},
                "display_name": "Tiles",
            },
            "tileset": {
                "srs": {"id": 3857},
                "source": {"id": "upload"},
            },
            "resmeta": {
                "items": {
                    "created_by": "NextGIS Connect/4.0.0",
                    "source": "/tmp/tiles.mbtiles",
                }
            },
        },
        is_lunkwill=True,
        feedback=None,
    )
    receive_resource.assert_called_once_with(
        connection,
        99,
        feedback=None,
    )
    tileset_constructor.assert_called_once_with(
        parent_resource.res_factory,
        received_resource,
    )


def test_tileset_layer_params_do_not_require_zoom_limits(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app
    tileset = _tileset({"srs": {"id": 3857}})
    connection = mock.Mock()
    connection.url = "https://example.test"
    connections_manager = mock.Mock()
    connections_manager.connection.return_value = connection
    monkeypatch.setattr(
        ngw_tileset,
        "NgwConnectionsManager",
        lambda: connections_manager,
    )

    uri, name, provider_key = tileset.layer_params
    parameters = (
        QgsProviderRegistry.instance().providerMetadata("wms").decodeUri(uri)
    )

    assert name == "Tiles"
    assert provider_key == "wms"
    assert "zmin" not in parameters
    assert "zmax" not in parameters


def test_tileset_layer_params_use_only_max_zoom(qgis_app, monkeypatch) -> None:
    del qgis_app
    tileset = _tileset({"srs": {"id": 3857}, "minzoom": 1, "maxzoom": 14})
    connection = mock.Mock()
    connection.url = "https://example.test"
    connections_manager = mock.Mock()
    connections_manager.connection.return_value = connection
    monkeypatch.setattr(
        ngw_tileset,
        "NgwConnectionsManager",
        lambda: connections_manager,
    )

    uri, _name, _provider_key = tileset.layer_params
    parameters = (
        QgsProviderRegistry.instance().providerMetadata("wms").decodeUri(uri)
    )

    assert "zmin" not in parameters
    assert parameters["zmax"] == "14"


def _tileset(tileset_payload: dict) -> NGWTileset:
    factory = mock.Mock()
    factory.connection.connection_id = "connection-id"
    return NGWTileset(
        factory,
        {
            "resource": {
                "id": 7,
                "cls": "tileset",
                "parent": None,
                "owner_user": None,
                "display_name": "Tiles",
                "description": "",
                "children": False,
                "interfaces": [],
            },
            "tileset": tileset_payload,
        },
    )
