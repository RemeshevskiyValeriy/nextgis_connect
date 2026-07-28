import shutil
import uuid
from unittest.mock import MagicMock

from qgis.core import QgsProject, QgsVectorLayer

from nextgis_connect.legacy.detached_editing.utils import (
    container_metadata,
    detached_layer_uri,
)
from nextgis_connect.legacy.ngw_connection import (
    NgwConnection,
    NgwConnectionsManager,
)
from nextgis_connect.legacy.ngw_resources_adder import NgwResourcesAdder
from nextgis_connect.legacy.settings.ng_connect_cache_manager import (
    NgConnectCacheManager,
)
from nextgis_connect.legacy.settings.ng_connect_settings import (
    NgConnectSettings,
)
from nextgis_connect.platform.filesystem import cp
from tests.detached_editing.utils import (
    mark_container_changed,
    mock_container,
    set_container_connection_metadata,
    set_container_version,
)
from tests.ng_connect_testcase import (
    NgConnectTestCase,
    TestConnection,
    TestData,
)


class TestCachedContainerLifecycle(NgConnectTestCase):
    def setUp(self) -> None:
        super().setUp()
        cache_manager = NgConnectCacheManager()
        self.cache_directory = self.create_temp_dir("-Cache")
        cache_manager.cache_directory = str(self.cache_directory)

    def tearDown(self) -> None:
        shutil.rmtree(str(self.cache_directory))
        super().tearDown()

    @mock_container(TestData.Points)
    def test_tree_add_rebinds_cached_container_after_connection_migration(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        ngw_layer = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self._move_to_cache(container_mock)
        obsolete_connection_id = str(uuid.uuid4())
        set_container_connection_metadata(
            container_path,
            connection_id=obsolete_connection_id,
        )

        layer_params = self._collect_detached_layer_params(ngw_layer)

        metadata = container_metadata(container_path)
        self.assertEqual(metadata.connection_id, connection.id)
        self.assertEqual(metadata.instance_id, connection.domain_uuid)
        self.assertFalse(metadata.has_changes)
        self.assertEqual(
            layer_params,
            (
                detached_layer_uri(container_path),
                ngw_layer.display_name,
                "ogr",
            ),
        )

    @mock_container(TestData.Points)
    def test_tree_add_rebinds_cached_container_with_local_changes(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        ngw_layer = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self._move_to_cache(container_mock)
        obsolete_connection_id = str(uuid.uuid4())
        set_container_connection_metadata(
            container_path,
            connection_id=obsolete_connection_id,
        )
        mark_container_changed(container_path)

        self._collect_detached_layer_params(ngw_layer)

        metadata = container_metadata(container_path)
        self.assertEqual(metadata.connection_id, connection.id)
        self.assertTrue(metadata.has_changes)

    @mock_container(TestData.Points)
    def test_tree_add_recreates_outdated_cached_container_without_changes(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        ngw_layer = self.resource(TestData.Points)
        container_path = self._move_to_cache(container_mock)
        set_container_version(container_path, "0.1.0")

        self._collect_detached_layer_params(ngw_layer)

        metadata = container_metadata(container_path)
        self.assertEqual(
            metadata.container_version,
            NgConnectSettings().supported_container_version,
        )
        self.assertTrue(metadata.is_not_initialized)
        self.assertEqual(metadata.features_count, 0)

    @mock_container(TestData.Points)
    def test_tree_add_rebinds_container_after_connection_recreation(
        self,
        container_mock: MagicMock,
        _qgs_layer: QgsVectorLayer,
    ) -> None:
        base_connection = self.connection(TestConnection.SandboxGuest)
        resource = self.resource(TestData.Points, base_connection)
        old_connection = NgwConnection(
            str(uuid.uuid4()),
            "Deleted connection",
            base_connection.url,
            None,
        )
        new_connection = NgwConnection(
            NgwConnection.domain_uuid_for_url(base_connection.url),
            "Recreated connection",
            base_connection.url,
            None,
        )
        self.assertNotEqual(old_connection.id, new_connection.id)
        self.assertEqual(
            old_connection.domain_uuid,
            new_connection.domain_uuid,
        )

        manager = NgwConnectionsManager()
        saved_connections = manager.connections
        saved_current_connection_id = manager.current_connection_id

        try:
            manager.replace_connections([old_connection])
            manager.current_connection_id = old_connection.id
            manager.save()

            cache_manager = NgConnectCacheManager()
            container_path = cache_manager.detached_container_path(
                old_connection.domain_uuid,
                resource.resource_id,
            )
            container_path.parent.mkdir(exist_ok=True, parents=True)
            cp(container_mock.path, container_path)
            set_container_connection_metadata(
                container_path,
                connection_id=old_connection.id,
                instance_id=old_connection.domain_uuid,
            )

            project_layer = QgsVectorLayer(
                detached_layer_uri(container_path),
                "cached layer",
                "ogr",
            )
            self.assertTrue(project_layer.isValid())
            QgsProject.instance().addMapLayer(project_layer)
            QgsProject.instance().removeMapLayer(project_layer.id())

            manager.remove(old_connection.id)
            manager.save()
            manager.upsert(new_connection)
            manager.current_connection_id = new_connection.id
            manager.save()

            ngw_layer = self.resource(TestData.Points, new_connection)
            layer_params = self._collect_detached_layer_params(ngw_layer)

            metadata = container_metadata(container_path)
            self.assertEqual(metadata.connection_id, new_connection.id)
            self.assertEqual(metadata.instance_id, new_connection.domain_uuid)
            self.assertEqual(
                layer_params,
                (
                    detached_layer_uri(container_path),
                    ngw_layer.display_name,
                    "ogr",
                ),
            )
        finally:
            manager.replace_connections(saved_connections)
            manager.current_connection_id = saved_current_connection_id
            manager.save()

    @mock_container(TestData.Points)
    def test_cache_migration_reassigns_cached_container_connection_id(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self._move_to_cache(container_mock)
        obsolete_connection_id = str(uuid.uuid4())
        set_container_connection_metadata(
            container_path,
            connection_id=obsolete_connection_id,
        )

        is_succeeded = (
            NgConnectCacheManager().reassign_container_connection_ids(
                [connection]
            )
        )

        metadata = container_metadata(container_path)
        self.assertTrue(is_succeeded)
        self.assertEqual(metadata.connection_id, connection.id)

    @mock_container(TestData.Points)
    def test_cache_migration_moves_reassigned_container_to_domain_cache_path(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        obsolete_connection_id = str(uuid.uuid4())
        legacy_container_path = (
            self.cache_directory
            / obsolete_connection_id
            / f"{resource.resource_id}.gpkg"
        )
        legacy_container_path.parent.mkdir(exist_ok=True, parents=True)
        cp(container_mock.path, legacy_container_path)
        set_container_connection_metadata(
            legacy_container_path,
            connection_id=obsolete_connection_id,
        )
        cache_manager = NgConnectCacheManager()
        canonical_container_path = cache_manager.detached_container_path(
            connection.domain_uuid,
            resource.resource_id,
        )

        is_succeeded = cache_manager.reassign_container_connection_ids(
            [connection]
        )

        metadata = container_metadata(canonical_container_path)
        self.assertTrue(is_succeeded)
        self.assertFalse(legacy_container_path.exists())
        self.assertTrue(canonical_container_path.exists())
        self.assertEqual(metadata.connection_id, connection.id)
        self.assertEqual(metadata.instance_id, connection.domain_uuid)

    @mock_container(TestData.Points)
    def test_cache_migration_skips_ambiguous_domain_connections(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        connection = self.connection(TestConnection.SandboxGuest)
        duplicate_connection = NgwConnection(
            str(uuid.uuid4()),
            "Duplicate sandbox",
            connection.url,
            None,
        )
        container_path = self._move_to_cache(container_mock)
        obsolete_connection_id = str(uuid.uuid4())
        set_container_connection_metadata(
            container_path,
            connection_id=obsolete_connection_id,
        )

        is_succeeded = (
            NgConnectCacheManager().reassign_container_connection_ids(
                [connection, duplicate_connection]
            )
        )

        metadata = container_metadata(container_path)
        self.assertTrue(is_succeeded)
        self.assertEqual(metadata.connection_id, obsolete_connection_id)

    def _move_to_cache(self, container_mock: MagicMock):
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        cache_manager = NgConnectCacheManager()
        container_path = cache_manager.detached_container_path(
            connection.domain_uuid,
            resource.resource_id,
        )
        container_path.parent.mkdir(exist_ok=True, parents=True)
        cp(container_mock.path, container_path)
        return container_path

    def _collect_detached_layer_params(self, ngw_layer):
        adder = NgwResourcesAdder.__new__(NgwResourcesAdder)
        return adder._NgwResourcesAdder__collect_params_for_detached_layer(
            ngw_layer
        )
