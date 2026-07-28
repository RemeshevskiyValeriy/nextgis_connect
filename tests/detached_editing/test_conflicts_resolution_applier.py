from dataclasses import replace
from typing import cast

from qgis.core import QgsVectorLayer, edit

from nextgis_connect.legacy.detached_editing.conflicts.conflict_resolution import (
    AttachmentConflictResolution,
    AttachmentResolutionData,
    ConflictResolution,
    DescriptionConflictResolution,
    FeatureConflictResolution,
    FeatureResolutionData,
    ResolutionType,
)
from nextgis_connect.legacy.detached_editing.conflicts.conflicts import (
    AttachmentDataConflict,
    DescriptionConflict,
    FeatureDataConflict,
    RemoteAttachmentDeletionConflict,
)
from nextgis_connect.legacy.detached_editing.conflicts.resolutions_applier import (
    ConflictsResolutionApplier,
)
from nextgis_connect.legacy.detached_editing.container.editing.container_sessions import (
    ContainerReadWriteSession,
)
from nextgis_connect.legacy.detached_editing.detached_layer import (
    DetachedLayer,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes_extractor import (
    ChangesExtractor,
)
from nextgis_connect.legacy.detached_editing.sync.common.serialization import (
    serialize_geometry,
)
from nextgis_connect.legacy.detached_editing.sync.versioned.actions import (
    AttachmentDeleteAction,
    AttachmentRestoreAction,
    AttachmentUpdateAction,
    DescriptionPutAction,
    FeatureRestoreAction,
    FeatureUpdateAction,
)
from nextgis_connect.legacy.detached_editing.utils import (
    AttachmentMetadata,
)
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestConflictsResolutionApplier(NgConnectTestCase):
    FEATURE_ID = 1
    ATTACHMENT_ID = 201

    def _extractor(self, container_mock) -> ChangesExtractor:
        return ChangesExtractor(container_mock.context)

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        descriptions={FEATURE_ID: "before"},
    )
    def test_apply_description_local_resolution_updates_remote_action(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)

        with edit(detached_layer.qgs_layer):
            detached_layer.set_feature_description(self.FEATURE_ID, "local")
        local_change = extractor.extract_updated_descriptions()[0]
        assert local_change.ngw_fid is not None
        remote_action = DescriptionPutAction(
            fid=local_change.ngw_fid,
            vid=21,
            value="remote",
        )
        conflict = DescriptionConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = DescriptionConflictResolution(
            resolution_type=ResolutionType.Local,
            conflict=conflict,
            value="local",
        )

        status, updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        updated_action = cast(DescriptionPutAction, updated_actions[0])
        self.assertEqual(updated_action.value, "local")
        description_change = extractor.extract_updated_descriptions()[0]
        self.assertEqual(description_change.description, "local")
        self.assertEqual(description_change.version, 21)

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        descriptions={FEATURE_ID: "before"},
    )
    def test_apply_description_remote_resolution_removes_local_marker(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)

        with edit(detached_layer.qgs_layer):
            detached_layer.set_feature_description(self.FEATURE_ID, "local")
        local_change = extractor.extract_updated_descriptions()[0]
        assert local_change.ngw_fid is not None
        remote_action = DescriptionPutAction(
            fid=local_change.ngw_fid,
            vid=21,
            value="remote",
        )
        conflict = DescriptionConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = DescriptionConflictResolution(
            resolution_type=ResolutionType.Remote,
            conflict=conflict,
            value="remote",
        )

        status, _updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(extractor.extract_updated_descriptions(), [])

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        attachments=[
            AttachmentMetadata(
                fid=FEATURE_ID,
                aid=ATTACHMENT_ID,
                ngw_aid=301,
                version=11,
                name="base-attachment",
                description="base-description",
                mime_type="text/plain",
                fileobj=901,
            )
        ],
    )
    def test_apply_local_resolution_for_remote_attachment_delete_restores_attachment(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)

        attachment = detached_layer.feature_attachment(
            self.FEATURE_ID,
            self.ATTACHMENT_ID,
        )
        assert attachment is not None

        with edit(qgs_layer):
            detached_layer.update_attachment(
                replace(attachment, name="local-name")
            )

        local_change = extractor.extract_updated_attachments()[0]
        remote_action = AttachmentDeleteAction(
            fid=local_change.ngw_fid,
            aid=local_change.ngw_aid,
            vid=51,
        )
        conflict = RemoteAttachmentDeletionConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = ConflictResolution(
            resolution_type=ResolutionType.Local,
            conflict=conflict,
        )

        status, updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(updated_actions, [])
        self.assertEqual(extractor.extract_updated_attachments(), [])
        restored_attachment = extractor.extract_restored_attachments()[0]
        self.assertEqual(restored_attachment.version, 51)

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_apply_feature_remote_resolution_removes_local_marker(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)
        string_field = container_mock.metadata.fields.get_with(
            keyname="STRING"
        )
        current_feature = next(detached_layer.qgs_layer.getFeatures())

        with edit(detached_layer.qgs_layer):
            self.assertTrue(
                detached_layer.qgs_layer.changeAttributeValue(
                    self.FEATURE_ID,
                    string_field.attribute,
                    "local-value",
                )
            )

        local_change = extractor.extract_updated_features()[0]
        remote_action = FeatureUpdateAction(
            fid=local_change.ngw_fid,
            vid=71,
            fields=[(string_field.ngw_id, "remote-value")],
        )
        conflict = FeatureDataConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = FeatureConflictResolution(
            resolution_type=ResolutionType.Remote,
            conflict=conflict,
            feature_data=FeatureResolutionData(
                fields=[
                    (
                        field.ngw_id,
                        current_feature.attribute(field.attribute),
                    )
                    for field in container_mock.metadata.fields
                ],
                geom=serialize_geometry(current_feature.geometry(), True),
            ),
        )

        status, updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(updated_actions, [remote_action])
        self.assertEqual(extractor.extract_updated_features(), [])

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_apply_feature_local_resolution_updates_feature_version(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)
        string_field = container_mock.metadata.fields.get_with(
            keyname="STRING"
        )
        current_feature = next(detached_layer.qgs_layer.getFeatures())

        with edit(detached_layer.qgs_layer):
            self.assertTrue(
                detached_layer.qgs_layer.changeAttributeValue(
                    self.FEATURE_ID,
                    string_field.attribute,
                    "local-value",
                )
            )

        local_change = extractor.extract_updated_features()[0]
        remote_action = FeatureUpdateAction(
            fid=local_change.ngw_fid,
            vid=72,
            fields=[(string_field.ngw_id, "remote-value")],
        )
        conflict = FeatureDataConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = FeatureConflictResolution(
            resolution_type=ResolutionType.Local,
            conflict=conflict,
            feature_data=FeatureResolutionData(
                fields=[
                    (
                        field.ngw_id,
                        current_feature.attribute(field.attribute),
                    )
                    for field in container_mock.metadata.fields
                ],
                geom=serialize_geometry(current_feature.geometry(), True),
            ),
        )

        status, _updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(extractor.extract_updated_features()[0].version, 72)

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        attachments=[
            AttachmentMetadata(
                fid=FEATURE_ID,
                aid=ATTACHMENT_ID,
                ngw_aid=301,
                version=11,
                name="base-attachment",
                description="base-description",
                mime_type="text/plain",
                fileobj=901,
            )
        ],
    )
    def test_apply_attachment_local_resolution_updates_attachment_version(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)

        attachment = detached_layer.feature_attachment(
            self.FEATURE_ID,
            self.ATTACHMENT_ID,
        )
        assert attachment is not None

        with edit(qgs_layer):
            detached_layer.update_attachment(
                replace(attachment, name="local-name")
            )

        local_change = extractor.extract_updated_attachments()[0]
        remote_action = AttachmentUpdateAction(
            fid=local_change.ngw_fid,
            aid=local_change.ngw_aid,
            vid=41,
            name="remote-name",
        )
        conflict = AttachmentDataConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolved_attachment = replace(attachment, name="local-name")
        resolution = AttachmentConflictResolution(
            resolution_type=ResolutionType.Local,
            conflict=conflict,
            attachment_data=AttachmentResolutionData.from_metadata(
                resolved_attachment,
            ),
        )

        status, _updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(
            extractor.extract_updated_attachments()[0].version, 41
        )

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_apply_feature_local_resolution_for_restore_conflict_converts_to_update(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)
        string_field = container_mock.metadata.fields.get_with(
            keyname="STRING"
        )

        with edit(detached_layer.qgs_layer):
            self.assertTrue(
                detached_layer.qgs_layer.changeAttributeValue(
                    self.FEATURE_ID,
                    string_field.attribute,
                    "local-restored-value",
                )
            )

        with ContainerReadWriteSession(container_mock.context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_updated_attributes WHERE fid = ?",
                (self.FEATURE_ID,),
            )
            cursor.execute(
                "DELETE FROM ngw_updated_geometries WHERE fid = ?",
                (self.FEATURE_ID,),
            )
            cursor.execute(
                "INSERT INTO ngw_restored_features (fid) VALUES (?)",
                (self.FEATURE_ID,),
            )

        local_change = extractor.extract_restored_features()[0]
        remote_action = FeatureRestoreAction(
            fid=local_change.ngw_fid,
            vid=82,
            fields=[(string_field.ngw_id, "remote-restored-value")],
        )
        conflict = FeatureDataConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = FeatureConflictResolution(
            resolution_type=ResolutionType.Local,
            conflict=conflict,
        )

        status, updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(len(updated_actions), 1)
        self.assertEqual(extractor.extract_restored_features(), [])
        updated_features = extractor.extract_updated_features()
        self.assertEqual(len(updated_features), 1)
        self.assertEqual(updated_features[0].version, 82)
        self.assertEqual(
            updated_features[0].fields_dict[string_field.ngw_id],
            "local-restored-value",
        )

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        attachments=[
            AttachmentMetadata(
                fid=FEATURE_ID,
                aid=ATTACHMENT_ID,
                ngw_aid=301,
                version=11,
                name="base-attachment",
                description="base-description",
                mime_type="text/plain",
                fileobj=901,
            )
        ],
    )
    def test_apply_attachment_local_resolution_for_restore_conflict_converts_to_update(
        self,
        container_mock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        detached_layer = DetachedLayer(container_mock, qgs_layer)
        extractor = self._extractor(container_mock)

        attachment = detached_layer.feature_attachment(
            self.FEATURE_ID,
            self.ATTACHMENT_ID,
        )
        assert attachment is not None

        with edit(qgs_layer):
            detached_layer.update_attachment(
                replace(attachment, name="local-restored-name")
            )

        with ContainerReadWriteSession(container_mock.context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_updated_attachments WHERE aid = ?",
                (self.ATTACHMENT_ID,),
            )
            cursor.execute(
                "INSERT INTO ngw_restored_attachments (aid) VALUES (?)",
                (self.ATTACHMENT_ID,),
            )

        local_change = extractor.extract_restored_attachments()[0]
        remote_action = AttachmentRestoreAction(
            fid=local_change.ngw_fid,
            aid=local_change.ngw_aid,
            vid=52,
            name="remote-restored-name",
        )
        conflict = AttachmentDataConflict(
            local_change=local_change,
            remote_action=remote_action,
        )
        resolution = AttachmentConflictResolution(
            resolution_type=ResolutionType.Local,
            conflict=conflict,
        )

        status, updated_actions = ConflictsResolutionApplier(
            container_mock.context
        ).apply([resolution], [remote_action])

        self.assertEqual(status, ConflictsResolutionApplier.Status.Resolved)
        self.assertEqual(len(updated_actions), 1)
        self.assertEqual(extractor.extract_restored_attachments(), [])
        updated_attachments = extractor.extract_updated_attachments()
        self.assertEqual(len(updated_attachments), 1)
        self.assertEqual(updated_attachments[0].version, 52)
        self.assertEqual(updated_attachments[0].name, "local-restored-name")
