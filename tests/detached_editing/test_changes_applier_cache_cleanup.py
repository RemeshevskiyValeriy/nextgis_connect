import json
import shutil
from pathlib import Path
from typing import Any, Sequence, Union
from unittest.mock import patch

from nextgis_connect.features.synchronization.infrastructure.storage.detached_storage_service import (
    DetachedStorageService,
)
from nextgis_connect.legacy.detached_editing.container.editing.container_sessions import (
    ContainerReadWriteSession,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes import (
    FeatureChange,
    FeatureDeletion,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes_applier import (
    ChangesApplier,
)
from nextgis_connect.legacy.detached_editing.utils import (
    DetachedContainerContext,
)
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class _TestChangesApplier(ChangesApplier):
    def apply(
        self,
        changes: Union[FeatureChange, Sequence[FeatureChange]],
        operation_result: Any = None,
    ) -> None:
        del changes
        del operation_result


class TestChangesApplierCacheCleanup(NgConnectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.cache_directory = self.create_temp_dir("-ConnectionCache")
        self.storage_service = DetachedStorageService(self.cache_directory)

    def tearDown(self) -> None:
        shutil.rmtree(str(self.cache_directory), ignore_errors=True)
        super().tearDown()

    @mock_container(TestData.Points)
    def test_process_deleted_features_removes_attachment_cache(
        self,
        container_mock,
        qgs_layer,
    ) -> None:
        del qgs_layer
        feature_id = 1
        feature_ngw_fid = 101
        attachment_id = 12
        attachment_fileobj = 501
        blob_path = self.storage_service.attachment_path(
            container_mock.metadata.instance_id,
            container_mock.metadata.resource_id,
            attachment_id,
            file_name="photo.jpg",
            mime_type="image/jpeg",
            fileobj=attachment_fileobj,
        )
        blob_path.parent.mkdir(parents=True, exist_ok=True)
        blob_path.write_bytes(b"blob")
        thumbnail_path = self.storage_service.attachment_thumbnail_path(
            container_mock.metadata.instance_id,
            container_mock.metadata.resource_id,
            attachment_id,
            fileobj=attachment_fileobj,
        )
        thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
        thumbnail_path.write_bytes(b"preview")
        self.storage_service.register_attachment_file(
            container_mock.metadata.instance_id,
            container_mock.metadata.resource_id,
            attachment_id,
            file_name="photo.jpg",
            mime_type="image/jpeg",
            fileobj=attachment_fileobj,
            feature_local_id=feature_id,
            feature_ngw_fid=feature_ngw_fid,
            ngw_aid=attachment_id,
        )
        self.storage_service.register_attachment_thumbnail(
            container_mock.metadata.instance_id,
            container_mock.metadata.resource_id,
            attachment_id,
            fileobj=attachment_fileobj,
            feature_local_id=feature_id,
            feature_ngw_fid=feature_ngw_fid,
            ngw_aid=attachment_id,
        )
        self._insert_removed_feature_backup(
            container_mock.path,
            feature_id,
            attachment_id,
            attachment_fileobj,
        )
        applier = _TestChangesApplier(
            DetachedContainerContext(
                path=container_mock.path,
                metadata=container_mock.metadata,
            )
        )

        with patch(
            "nextgis_connect.legacy.detached_editing.sync.common.changes_applier.DetachedStorageServiceFactory.create",
            return_value=self.storage_service,
        ):
            applier._process_deleted_features(
                [
                    FeatureDeletion(
                        fid=feature_id,
                        ngw_fid=feature_ngw_fid,
                    )
                ]
            )

        self.assertFalse(blob_path.exists())
        self.assertFalse(thumbnail_path.exists())

    def _insert_removed_feature_backup(
        self,
        container_path: Path,
        feature_id: int,
        attachment_id: int,
        attachment_fileobj: int,
    ) -> None:
        attachment_backup = {
            "aid": attachment_id,
            "fileobj": json.dumps(attachment_fileobj),
        }
        backup = {
            "before_deletion": {"attachments": [attachment_backup]},
            "after_sync": {"attachments": [attachment_backup]},
        }
        with ContainerReadWriteSession(container_path) as cursor:
            cursor.execute(
                """
                INSERT INTO ngw_removed_features (fid, backup)
                VALUES (?, ?)
                """,
                (feature_id, json.dumps(backup)),
            )
