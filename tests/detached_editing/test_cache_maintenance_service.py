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

import os
import shutil
import time
from contextlib import closing
from pathlib import Path
from unittest.mock import MagicMock, patch

from qgis.core import QgsProject, QgsVectorLayer

from nextgis_connect.features.synchronization.infrastructure.storage.cache_maintenance_service import (
    CacheMaintenanceService,
)
from nextgis_connect.features.synchronization.infrastructure.storage.detached_storage_service import (
    DetachedStorageService,
)
from nextgis_connect.legacy.detached_editing.utils import (
    container_metadata,
    detached_layer_uri,
    make_connection,
)
from nextgis_connect.legacy.settings.tasks.clear_ng_connect_cache_task import (
    ClearNgConnectCacheTask,
)
from nextgis_connect.platform.storage.file_store import FileStore
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    LayerKey,
    StorageEntryKind,
    StorageEntryProtection,
    StorageEntryState,
)
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)
from nextgis_connect.platform.storage.storage_key import StorageKeyFactory
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import (
    NgConnectTestCase,
    TestConnection,
    TestData,
)


class TestCacheMaintenanceService(NgConnectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cache_service = CacheMaintenanceService()
        self.cache_directory = self.create_temp_dir("-ConnectionCache")
        self.cache_service.cache_directory = str(self.cache_directory)
        self.storage_service = DetachedStorageService(self.cache_directory)

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
        self.__register_container_in_index(container_path)
        unindexed_container_path = (
            self.cache_directory / connection.domain_uuid / "unindexed.gpkg"
        )
        unindexed_container_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(container_mock.path, unindexed_container_path)
        self.__mark_container_changed(unindexed_container_path)

        changed_containers = self.cache_service.containers_with_changes(
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

        self.assertTrue(self.cache_service.clear_connection_cache(connection))

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
                self.cache_service.containers_used_by_project(connection),
                [
                    (
                        container_path,
                        f"{metadata.layer_name} (id={metadata.resource_id})",
                    )
                ],
            )
            self.assertEqual(
                self.cache_service.containers_used_by_project(
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
                self.cache_service.containers_used_by_project(), []
            )
            self.assertEqual(
                self.cache_service.containers_used_by_project(
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
                self.cache_service.clear_connection_cache(connection)
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
        canonical_container_path = (
            self.storage_service.ensure_container_placeholder(
                connection.domain_uuid,
                resource.resource_id,
            )
        )

        result = self.storage_service.canonical_container_path(
            connection.domain_uuid,
            resource.resource_id,
            connection_id=connection.id,
            source_container_path=legacy_container_path,
        )

        canonical_service_file = canonical_container_path.parent / (
            f"{canonical_container_path.name}-wal"
        )
        self.assertEqual(result, canonical_container_path)
        self.assertFalse(legacy_container_path.exists())
        self.assertFalse(legacy_service_file.exists())
        self.assertTrue(canonical_container_path.exists())
        self.assertTrue(canonical_service_file.exists())

    @mock_container(TestData.Points)
    def test_register_detached_container_updates_storage_index(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.__copy_container_to_cache(container_mock)

        is_registered = self.storage_service.register_detached_container(
            connection.domain_uuid,
            resource.resource_id,
            connection_id=connection.id,
            container_path=container_path,
        )

        storage_index = self.__storage_index()
        layer_entry = storage_index.layer_entry(
            LayerKey(connection.domain_uuid, resource.resource_id)
        )
        self.assertTrue(is_registered)
        self.assertIsNotNone(layer_entry)
        assert layer_entry is not None
        self.assertEqual(layer_entry["connection_id"], connection.id)

        container_entry = storage_index.find_entry_by_id(
            int(layer_entry["container_entry_id"])
        )
        self.assertIsNotNone(container_entry)
        assert container_entry is not None
        self.assertEqual(
            container_entry.kind, StorageEntryKind.LAYER_CONTAINER
        )
        self.assertEqual(container_entry.state, StorageEntryState.COMMITTED)
        self.assertEqual(
            container_entry.protection, StorageEntryProtection.NONE
        )
        self.assertEqual(
            container_entry.size_bytes, container_path.stat().st_size
        )
        self.assertIsNotNone(container_entry.sha256)

    @mock_container(TestData.Points)
    def test_reassign_connection_updates_index_metadata(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.__copy_container_to_cache(container_mock)
        metadata = container_metadata(container_path)
        with closing(make_connection(container_path)) as database_connection:
            database_connection.execute(
                "UPDATE ngw_metadata SET connection_id = ?",
                ("legacy-connection",),
            )
            database_connection.commit()
        self.storage_service.register_detached_container(
            connection.domain_uuid,
            metadata.resource_id,
            connection_id="legacy-connection",
            container_path=container_path,
        )

        result = self.cache_service.reassign_container_connection_ids(
            [connection]
        )

        layer_entry = self.__storage_index().layer_entry(
            LayerKey(connection.domain_uuid, metadata.resource_id)
        )
        self.assertTrue(result)
        self.assertIsNotNone(layer_entry)
        assert layer_entry is not None
        self.assertEqual(layer_entry["connection_id"], connection.id)
        self.assertEqual(
            container_metadata(container_path).connection_id,
            connection.id,
        )

    def test_register_attachment_file_and_thumbnail_updates_storage_index(
        self,
    ) -> None:
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        attachment_id = 12
        fileobj = 345
        blob_path = self.storage_service.attachment_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="photo.jpg",
            mime_type="image/jpeg",
            fileobj=fileobj,
        )
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(b"blob")
        thumbnail_path = self.storage_service.attachment_thumbnail_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path.write_bytes(b"preview")

        is_blob_registered = self.storage_service.register_attachment_file(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="photo.jpg",
            mime_type="image/jpeg",
            fileobj=fileobj,
            feature_local_id=1,
            feature_ngw_fid=101,
            ngw_aid=attachment_id,
        )
        is_thumbnail_registered = (
            self.storage_service.register_attachment_thumbnail(
                connection.domain_uuid,
                resource.resource_id,
                attachment_id,
                fileobj=fileobj,
                feature_local_id=1,
                feature_ngw_fid=101,
                ngw_aid=attachment_id,
            )
        )

        storage_index = self.__storage_index()
        record = storage_index.attachment_record(
            AttachmentKey(
                instance_uuid=connection.domain_uuid,
                resource_id=resource.resource_id,
                feature_local_id=1,
                feature_ngw_fid=101,
                local_attachment_id=str(attachment_id),
                ngw_aid=attachment_id,
            )
        )
        self.assertTrue(is_blob_registered)
        self.assertTrue(is_thumbnail_registered)
        self.assertIsNotNone(record)
        assert record is not None

        blob_entry = storage_index.find_entry_by_id(
            int(record["active_blob_entry_id"])
        )
        preview_entry = storage_index.find_entry_by_id(
            int(record["preview_entry_id"])
        )
        self.assertIsNotNone(blob_entry)
        self.assertIsNotNone(preview_entry)
        assert blob_entry is not None
        assert preview_entry is not None
        self.assertEqual(blob_entry.kind, StorageEntryKind.ATTACHMENT_BLOB)
        self.assertEqual(
            preview_entry.kind, StorageEntryKind.ATTACHMENT_PREVIEW
        )
        self.assertEqual(blob_entry.state, StorageEntryState.COMMITTED)
        self.assertEqual(blob_entry.protection, StorageEntryProtection.NONE)

    def test_cached_attachment_path_uses_indexed_blob_path(self) -> None:
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        attachment_id = 12
        fileobj = 345
        blob_path = self.storage_service.attachment_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="photo.jpg",
            mime_type="image/jpeg",
            fileobj=fileobj,
        )
        changed_canonical_path = self.storage_service.attachment_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="photo.png",
            mime_type="image/png",
            fileobj=fileobj,
        )
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(b"blob")
        self.storage_service.register_attachment_file(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="photo.jpg",
            mime_type="image/jpeg",
            fileobj=fileobj,
            feature_local_id=1,
            feature_ngw_fid=101,
            ngw_aid=attachment_id,
        )

        fresh_storage_service = DetachedStorageService(self.cache_directory)
        cached_path = fresh_storage_service.cached_attachment_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="photo.png",
            mime_type="image/png",
            fileobj=fileobj,
            feature_local_id=1,
            feature_ngw_fid=101,
            ngw_aid=attachment_id,
        )

        self.assertNotEqual(changed_canonical_path, blob_path)
        self.assertEqual(cached_path, blob_path)
        self.assertTrue(cached_path.exists())

    def test_cached_attachment_thumbnail_path_uses_indexed_preview(
        self,
    ) -> None:
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        attachment_id = 12
        fileobj = 345
        thumbnail_path = self.storage_service.attachment_thumbnail_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path.write_bytes(b"preview")
        self.storage_service.register_attachment_thumbnail(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            fileobj=fileobj,
            feature_local_id=1,
            feature_ngw_fid=101,
            ngw_aid=attachment_id,
        )

        fresh_storage_service = DetachedStorageService(self.cache_directory)
        cached_path = fresh_storage_service.cached_attachment_thumbnail_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            fileobj=fileobj,
            feature_local_id=1,
            feature_ngw_fid=101,
            ngw_aid=attachment_id,
        )

        self.assertEqual(cached_path, thumbnail_path)
        self.assertTrue(cached_path.exists())

    def test_move_attachment_cache_to_fileobj_reindexes_file(self) -> None:
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        attachment_id = 13
        new_fileobj = 456
        old_blob_directory = self.storage_service.attachment_directory(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
        )
        blob_path = self.storage_service.attachment_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="document.txt",
            mime_type="text/plain",
        )
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_text("blob")
        thumbnail_path = self.storage_service.attachment_thumbnail_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
        )
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path.write_bytes(b"preview")
        self.storage_service.register_attachment_file(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="document.txt",
            mime_type="text/plain",
            is_dirty=True,
        )
        self.storage_service.register_attachment_thumbnail(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
        )

        self.storage_service.move_attachment_cache_to_fileobj(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            old_fileobj=None,
            new_fileobj=new_fileobj,
        )

        storage_index = self.__storage_index()
        local_storage_key = StorageKeyFactory.local_attachment_blob(
            connection.domain_uuid,
            resource.resource_id,
            str(attachment_id),
        )
        remote_storage_key = StorageKeyFactory.remote_attachment_blob(
            connection.domain_uuid,
            resource.resource_id,
            new_fileobj,
        )
        remote_entry = storage_index.find_entry(remote_storage_key)
        remote_blob_path = self.storage_service.attachment_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            file_name="document.txt",
            mime_type="text/plain",
            fileobj=new_fileobj,
        )
        remote_thumbnail_path = self.storage_service.attachment_thumbnail_path(
            connection.domain_uuid,
            resource.resource_id,
            attachment_id,
            fileobj=new_fileobj,
        )
        self.assertFalse(old_blob_directory.exists())
        self.assertTrue(remote_blob_path.exists())
        self.assertTrue(remote_thumbnail_path.exists())
        self.assertIsNone(storage_index.find_entry(local_storage_key))
        self.assertIsNotNone(remote_entry)
        assert remote_entry is not None
        self.assertEqual(remote_entry.state, StorageEntryState.COMMITTED)
        self.assertEqual(remote_entry.protection, StorageEntryProtection.NONE)

    def test_cache_size_ignores_storage_metadata_files(self) -> None:
        connection = self.connection(TestConnection.SandboxGuest)
        storage_index = self.__storage_index()
        (self.cache_directory / "storage.sqlite-backup").write_bytes(
            b"x" * 2048
        )
        storage_key = StorageKeyFactory.remote_attachment_blob(
            connection.domain_uuid,
            self.resource(TestData.Points).resource_id,
            1,
        )
        blob_ref = FileStore(
            StoragePathResolver(self.cache_directory),
            storage_index,
        ).write_bytes(
            storage_key,
            "blob",
            b"x" * 1024,
            kind=StorageEntryKind.ATTACHMENT_BLOB,
            resource_id=self.resource(TestData.Points).resource_id,
            state=StorageEntryState.COMMITTED,
            protection=StorageEntryProtection.NONE,
        )

        self.assertEqual(self.cache_service.cache_size, 1)
        assert blob_ref.entry_id is not None
        storage_index.delete_entry(blob_ref.entry_id)
        self.assertEqual(self.cache_service.cache_size, 0)

    def test_purge_cache_removes_stale_download_temporary_file(self) -> None:
        self.cache_service.cache_duration = -1
        self.cache_service.cache_max_size = -1
        temporary_path = self.cache_directory / "attachment.download"
        temporary_path.write_bytes(b"partial")
        old_time = (
            time.time()
            - CacheMaintenanceService.TEMPORARY_CACHE_MAX_AGE_SECONDS
            - 1
        )
        os.utime(temporary_path, (old_time, old_time))

        self.assertTrue(self.cache_service.purge_cache())

        self.assertFalse(temporary_path.exists())

    def test_clear_cache_task_returns_cache_service_result(self) -> None:
        with patch(
            "nextgis_connect.legacy.settings.tasks.clear_ng_connect_cache_task.CacheMaintenanceService"
        ) as cache_service_class:
            cache_service_class.return_value.clear_cache.return_value = False

            self.assertFalse(ClearNgConnectCacheTask().run())

    def __copy_container_to_cache(self, container_mock: MagicMock):
        resource = self.resource(TestData.Points)
        connection = self.connection(TestConnection.SandboxGuest)
        container_path = self.storage_service.ensure_container_placeholder(
            connection.domain_uuid,
            resource.resource_id,
        )
        container_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(container_mock.path, container_path)
        return container_path

    def __register_container_in_index(self, container_path: Path) -> None:
        metadata = container_metadata(container_path)
        self.storage_service.register_detached_container(
            metadata.instance_id,
            metadata.resource_id,
            connection_id=metadata.connection_id,
            container_path=container_path,
        )

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

    def __storage_index(self) -> SqliteStorageIndex:
        path_resolver = StoragePathResolver(Path(self.cache_directory))
        storage_index = SqliteStorageIndex(path_resolver.index_path())
        storage_index.initialize()
        return storage_index
