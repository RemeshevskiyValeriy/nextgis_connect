import shutil
from contextlib import closing
from unittest.mock import MagicMock

from qgis.core import QgsProject, QgsVectorLayer

from nextgis_connect.legacy.detached_editing.utils import (
    container_metadata,
    detached_layer_uri,
    make_connection,
)
from nextgis_connect.legacy.settings.ng_connect_cache_manager import (
    NgConnectCacheManager,
)
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import (
    NgConnectTestCase,
    TestConnection,
    TestData,
)


class TestConnectionCacheManager(NgConnectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cache_manager = NgConnectCacheManager()
        self.cache_directory = self.create_temp_dir("-ConnectionCache")
        self.cache_manager.cache_directory = str(self.cache_directory)

    def tearDown(self) -> None:
        shutil.rmtree(str(self.cache_directory), ignore_errors=True)
        super().tearDown()

    @mock_container(TestData.Points)
    def test_containers_with_changes_filters_connection_cache(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.__copy_container_to_cache(container_mock)
        self.__mark_container_changed(container_path)

        changed_containers = self.cache_manager.containers_with_changes(
            connection
        )

        metadata = container_metadata(container_path)
        self.assertEqual(
            changed_containers,
            [
                (
                    container_path,
                    f"{metadata.layer_name} (id={metadata.resource_id})",
                )
            ],
        )

    @mock_container(TestData.Points)
    def test_clear_connection_cache_removes_connection_cache(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.__copy_container_to_cache(container_mock)

        self.assertTrue(self.cache_manager.clear_connection_cache(connection))

        self.assertFalse(container_path.exists())

    @mock_container(TestData.Points)
    def test_containers_used_by_project_filters_connection_cache(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.__copy_container_to_cache(container_mock)
        project_layer = self.__add_container_to_project(container_path)

        try:
            metadata = container_metadata(container_path)
            self.assertEqual(
                self.cache_manager.containers_used_by_project(connection),
                [
                    (
                        container_path,
                        f"{metadata.layer_name} (id={metadata.resource_id})",
                    )
                ],
            )
            self.assertEqual(
                self.cache_manager.containers_used_by_project(
                    self.connection(TestConnection.DemoGuest)
                ),
                [],
            )
        finally:
            QgsProject.instance().removeMapLayer(project_layer.id())

    @mock_container(TestData.Points)
    def test_containers_used_by_project_ignores_non_cache_container(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        external_directory = self.create_temp_dir("-ExternalContainer")
        container_path = external_directory / "external.gpkg"
        shutil.copyfile(container_mock.path, container_path)
        project_layer = self.__add_container_to_project(container_path)

        try:
            self.assertEqual(
                self.cache_manager.containers_used_by_project(), []
            )
            self.assertEqual(
                self.cache_manager.containers_used_by_project(
                    self.connection(TestConnection.SandboxGuest)
                ),
                [],
            )
        finally:
            QgsProject.instance().removeMapLayer(project_layer.id())

    @mock_container(TestData.Points)
    def test_clear_connection_cache_keeps_project_container(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.__copy_container_to_cache(container_mock)
        project_layer = self.__add_container_to_project(container_path)

        try:
            self.assertFalse(
                self.cache_manager.clear_connection_cache(connection)
            )
            self.assertTrue(container_path.exists())
        finally:
            QgsProject.instance().removeMapLayer(project_layer.id())

    @mock_container(TestData.Points)
    def test_canonical_detached_container_path_moves_legacy_cache_container(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        legacy_container_path = (
            self.cache_directory
            / connection.id
            / f"{resource.resource_id}.gpkg"
        )
        legacy_container_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(container_mock.path, legacy_container_path)
        legacy_service_file = legacy_container_path.parent / (
            f"{legacy_container_path.name}-wal"
        )
        legacy_service_file.touch()
        canonical_container_path = self.cache_manager.detached_container_path(
            connection.domain_uuid,
            resource.resource_id,
        )

        result = self.cache_manager.canonical_detached_container_path(
            connection,
            resource.resource_id,
            legacy_container_path,
        )

        canonical_service_file = canonical_container_path.parent / (
            f"{canonical_container_path.name}-wal"
        )
        self.assertEqual(result, canonical_container_path)
        self.assertFalse(legacy_container_path.exists())
        self.assertFalse(legacy_service_file.exists())
        self.assertTrue(canonical_container_path.exists())
        self.assertTrue(canonical_service_file.exists())

    def __copy_container_to_cache(self, container_mock: MagicMock):
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.cache_manager.detached_container_path(
            connection.domain_uuid,
            resource.resource_id,
        )
        container_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(container_mock.path, container_path)
        return container_path

    def __add_container_to_project(self, container_path):
        metadata = container_metadata(container_path)
        layer = QgsVectorLayer(
            detached_layer_uri(container_path, metadata),
            metadata.layer_name,
            "ogr",
        )
        self.assertTrue(layer.isValid())
        QgsProject.instance().addMapLayer(layer)
        return layer

    def __mark_container_changed(self, container_path) -> None:
        metadata = container_metadata(container_path)
        attribute = next(iter(metadata.fields)).attribute
        with closing(make_connection(container_path)) as connection:
            cursor = connection.cursor()
            cursor.execute(
                """
                INSERT INTO ngw_updated_attributes (fid, attribute, backup)
                VALUES (?, ?, ?)
                """,
                (1, attribute, "previous"),
            )
            connection.commit()
