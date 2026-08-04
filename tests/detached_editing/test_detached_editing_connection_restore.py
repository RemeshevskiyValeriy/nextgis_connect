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
from unittest.mock import MagicMock, patch
from uuid import uuid4

from qgis.core import QgsProject, QgsVectorLayer

from nextgis_connect.legacy.detached_editing.detached_editing import (
    DetachedEditing,
)
from nextgis_connect.legacy.ngw_connection import (
    ConnectionUpdateState,
    NgwConnection,
)
from tests.ng_connect_testcase import NgConnectTestCase


class _Layer:
    def __init__(self, properties):
        self._properties = properties

    def customProperty(self, key):
        return self._properties.get(key)


def test_layer_matches_connection_by_old_connection_id() -> None:
    detached_editing = DetachedEditing.__new__(DetachedEditing)
    connection = NgwConnection(
        "current-id",
        "Current",
        "https://current.nextgis.com/",
        None,
        ("old-id",),
    )

    assert detached_editing._DetachedEditing__layer_belongs_to_connection(
        _Layer({"ngw_connection_id": "old-id"}),
        Path("/tmp/old-id/123.gpkg"),
        connection,
    )


def test_layer_matches_connection_by_domain_cache_path() -> None:
    detached_editing = DetachedEditing.__new__(DetachedEditing)
    connection = NgwConnection(
        "current-id",
        "Current",
        "https://current.nextgis.com/",
        None,
    )
    container_path = Path("/tmp/cache") / connection.domain_uuid / "123.gpkg"

    assert detached_editing._DetachedEditing__layer_belongs_to_connection(
        _Layer({}),
        container_path,
        connection,
    )


class TestDetachedEditingConnectionRestore(NgConnectTestCase):
    def tearDown(self) -> None:
        QgsProject.instance().removeAllMapLayers()
        super().tearDown()

    def test_connection_created_restores_all_layers_for_container(
        self,
    ) -> None:
        connection = NgwConnection(
            "current-id",
            "Current",
            "https://current.nextgis.com/",
            None,
        )
        source_path = Path("/tmp/old-id/123.gpkg")
        restored_path = Path("/tmp/cache/current/123.gpkg")
        handled_layer = self.__memory_layer("handled", connection.domain_uuid)
        related_layer = self.__memory_layer("related", connection.domain_uuid)
        unrelated_layer = self.__memory_layer("unrelated", str(uuid4()))
        QgsProject.instance().addMapLayers(
            [handled_layer, related_layer, unrelated_layer],
            False,
        )

        layer_paths = {
            handled_layer.id(): source_path,
            related_layer.id(): source_path,
            unrelated_layer.id(): source_path,
        }
        restored_layer_ids = []
        detached_editing = DetachedEditing.__new__(DetachedEditing)
        detached_editing._DetachedEditing__containers_by_layer_id = {}

        def layer_container_path(layer):
            return layer_paths.get(layer.id())

        def restore_layer_source(layer, path):
            restored_layer_ids.append(layer.id())
            layer_paths[layer.id()] = path

        def handle_connection_updated(layer, updated_connection, is_new):
            if layer is not handled_layer:
                return None

            assert updated_connection == connection
            assert is_new
            restore_layer_source(layer, restored_path)
            return restored_path

        detached_editing._DetachedEditing__layer_container_path = (
            layer_container_path
        )
        detached_editing._DetachedEditing__restore_layer_source = (
            restore_layer_source
        )
        handle_attr = "_DetachedEditing__handle_connection_updated_for_layer"
        setattr(detached_editing, handle_attr, handle_connection_updated)
        detached_editing._DetachedEditing__setup_layer = lambda _layer: True
        detached_editing._DetachedEditing__add_indicator_if_needed = (
            lambda _layer: None
        )

        with patch(
            "nextgis_connect.legacy.detached_editing.detached_editing.NgwConnectionsManager"
        ) as manager_class:
            manager_class.return_value.connection.return_value = connection

            detached_editing.on_connection_updated(
                connection.id,
                ConnectionUpdateState.CREATED,
            )

        self.assertEqual(
            restored_layer_ids,
            [handled_layer.id(), related_layer.id()],
        )
        self.assertEqual(layer_paths[handled_layer.id()], restored_path)
        self.assertEqual(layer_paths[related_layer.id()], restored_path)
        self.assertEqual(layer_paths[unrelated_layer.id()], source_path)

    def test_legacy_connection_id_metadata_is_refreshed(self) -> None:
        connection = NgwConnection(
            "current-id",
            "Current",
            "https://current.nextgis.com/",
            None,
            ("old-id",),
        )
        source_path = Path("/tmp/old-id/123.gpkg")
        layer = self.__memory_layer("legacy", connection.domain_uuid)
        layer.setCustomProperty("ngw_connection_id", "old-id")
        container = MagicMock()
        container.metadata.connection_id = "old-id"
        detached_editing = DetachedEditing.__new__(DetachedEditing)
        detached_editing._DetachedEditing__containers_by_layer_id = {
            layer.id(): container
        }
        detached_editing._DetachedEditing__layer_container_path = (
            lambda _layer: source_path
        )
        detached_editing._DetachedEditing__restored_container_path = (
            lambda *_args: source_path
        )
        detached_editing._DetachedEditing__prepare_connection_container = (
            lambda *_args: (True, False)
        )
        detached_editing._DetachedEditing__restore_layer_source = MagicMock()

        with patch(
            "nextgis_connect.legacy.detached_editing.detached_editing.utils.is_ngw_container",
            return_value=True,
        ):
            with patch(
                "nextgis_connect.legacy.detached_editing.detached_editing.NgwConnectionsManager"
            ) as manager_class:
                manager_class.return_value.connection.side_effect = (
                    lambda connection_id: (
                        connection
                        if connection.matches_id(connection_id)
                        else None
                    )
                )

                handle_attr = (
                    "_DetachedEditing__handle_connection_updated_for_layer"
                )
                handle_connection_updated = getattr(
                    detached_editing,
                    handle_attr,
                )
                restored_path = handle_connection_updated(
                    layer,
                    connection,
                    True,
                )

        self.assertEqual(restored_path, source_path)
        container.update_connection.assert_called_once_with(
            connection.id,
            connection.domain_uuid,
        )
        container.refresh_additional_data.assert_called_once_with()

    def test_missing_container_is_restored_to_connection_cache_path(
        self,
    ) -> None:
        connection = NgwConnection(
            "current-id",
            "Current",
            "https://current.nextgis.com/",
            None,
        )
        source_path = Path("/tmp/old-id/123.gpkg")
        restored_path = Path("/tmp/cache/current/123.gpkg")
        detached_editing = DetachedEditing.__new__(DetachedEditing)

        with patch(
            "nextgis_connect.legacy.detached_editing.detached_editing.DetachedStorageServiceFactory"
        ) as storage_factory:
            storage_service = storage_factory.create.return_value
            storage_service.canonical_container_path.return_value = (
                restored_path
            )

            result = (
                detached_editing._DetachedEditing__restored_container_path(
                    connection,
                    123,
                    source_path,
                )
            )

        self.assertEqual(result, restored_path)
        storage_service.canonical_container_path.assert_called_once_with(
            connection.domain_uuid,
            123,
            connection_id=connection.id,
            source_container_path=source_path,
        )

    def __memory_layer(self, name: str, instance_id: str) -> QgsVectorLayer:
        layer = QgsVectorLayer("Point", name, "memory")
        layer.setCustomProperty("ngw_instance_id", instance_id)
        layer.setCustomProperty("ngw_resource_id", "123")
        return layer
