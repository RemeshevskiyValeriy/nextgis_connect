from qgis.core import QgsFeature, QgsGeometry, QgsVectorLayer, edit

from nextgis_connect.legacy.detached_editing.container.editing.container_sessions import (
    ContainerReadWriteSession,
)
from nextgis_connect.legacy.detached_editing.detached_layer import (
    DetachedLayer,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes import (
    AttachmentCreation,
    AttachmentDeletion,
    AttachmentRestoration,
    AttachmentUpdate,
    DescriptionPut,
    FeatureCreation,
    FeatureDeletion,
    FeatureRestoration,
    FeatureUpdate,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes_extractor import (
    ChangesExtractor,
)
from nextgis_connect.legacy.detached_editing.utils import (
    AttachmentMetadata,
    DetachedContainerContext,
)
from nextgis_connect.ngw.resources.ngw_data_type import NgwDataType
from nextgis_connect.platform.qgis.errors import (
    ErrorCode,
    SynchronizationError,
)
from nextgis_connect.shared.types import Unset
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestChangesExtraction(NgConnectTestCase):
    FEATURE_1 = 1

    def _extractor(self, container_mock) -> ChangesExtractor:
        context = DetachedContainerContext(
            path=container_mock.path,
            metadata=container_mock.metadata,
        )
        return ChangesExtractor(context)

    def _first_feature_id(self, qgs_layer: QgsVectorLayer) -> int:
        feature_ids = sorted(qgs_layer.allFeatureIds())
        self.assertGreater(len(feature_ids), 0)
        return feature_ids[0]

    def _string_attribute_index(self, qgs_layer: QgsVectorLayer) -> int:
        attribute_index = qgs_layer.fields().indexOf("STRING")
        self.assertNotEqual(attribute_index, -1)
        return attribute_index

    @mock_container(TestData.Points)
    def test_extract_added_features_returns_feature_creation(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        string_attribute = self._string_attribute_index(layer.qgs_layer)
        expected_geometry = QgsGeometry.fromWkt("Point (10 20)")

        with edit(layer.qgs_layer):
            new_feature = QgsFeature(layer.qgs_layer.fields())
            new_feature.setAttribute(string_attribute, "created")
            new_feature.setGeometry(expected_geometry)
            self.assertTrue(layer.qgs_layer.addFeature(new_feature))

        result = extractor.extract_added_features()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FeatureCreation)
        assert isinstance(result[0], FeatureCreation)
        field = container_mock.metadata.fields.get_with(
            attribute=string_attribute
        )
        self.assertEqual(result[0].fields_dict[field.ngw_id], "created")
        self.assertIsNot(result[0].geometry, Unset)
        assert isinstance(result[0].geometry, QgsGeometry)
        self.assertTrue(result[0].geometry.equals(expected_geometry))

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_extract_updated_features_returns_feature_update(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        feature_id = self._first_feature_id(layer.qgs_layer)
        string_attribute = self._string_attribute_index(layer.qgs_layer)
        expected_geometry = QgsGeometry.fromWkt("Point (30 40)")

        with edit(layer.qgs_layer):
            self.assertTrue(
                layer.qgs_layer.changeAttributeValue(
                    feature_id, string_attribute, "updated"
                )
            )
            self.assertTrue(
                layer.qgs_layer.changeGeometry(feature_id, expected_geometry)
            )

        result = extractor.extract_updated_features()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FeatureUpdate)
        assert isinstance(result[0], FeatureUpdate)
        field = container_mock.metadata.fields.get_with(
            attribute=string_attribute
        )
        self.assertEqual(result[0].fid, feature_id)
        self.assertIsNotNone(result[0].ngw_fid)
        self.assertEqual(result[0].fields_dict[field.ngw_id], "updated")
        self.assertIsNot(result[0].geometry, Unset)
        assert isinstance(result[0].geometry, QgsGeometry)
        self.assertTrue(result[0].geometry.equals(expected_geometry))

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_extract_updated_features_field_only_leaves_geometry_unset(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        feature_id = self._first_feature_id(layer.qgs_layer)
        string_attribute = self._string_attribute_index(layer.qgs_layer)

        with edit(layer.qgs_layer):
            self.assertTrue(
                layer.qgs_layer.changeAttributeValue(
                    feature_id, string_attribute, "field-only"
                )
            )

        result = extractor.extract_updated_features()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FeatureUpdate)
        self.assertIs(result[0].geometry, Unset)
        self.assertNotEqual(result[0].fields, Unset)

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_extract_updated_features_geometry_only_leaves_fields_unset(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        feature_id = self._first_feature_id(layer.qgs_layer)
        expected_geometry = QgsGeometry.fromWkt("Point (55 66)")

        with edit(layer.qgs_layer):
            self.assertTrue(
                layer.qgs_layer.changeGeometry(feature_id, expected_geometry)
            )

        result = extractor.extract_updated_features()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FeatureUpdate)
        self.assertIs(result[0].fields, Unset)
        self.assertIsNot(result[0].geometry, Unset)
        assert isinstance(result[0].geometry, QgsGeometry)
        self.assertTrue(result[0].geometry.equals(expected_geometry))

    @mock_container(TestData.Points)
    def test_extract_deleted_features_returns_feature_deletion(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        feature_id = self._first_feature_id(layer.qgs_layer)

        with edit(layer.qgs_layer):
            self.assertTrue(layer.qgs_layer.deleteFeature(feature_id))

        result = extractor.extract_deleted_features()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FeatureDeletion)
        assert isinstance(result[0], FeatureDeletion)
        self.assertEqual(result[0].fid, feature_id)
        self.assertIsNotNone(result[0].ngw_fid)

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_extract_restored_features_returns_feature_restoration(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        feature_id = self._first_feature_id(qgs_layer)

        with ContainerReadWriteSession(container_mock.path) as cursor:
            cursor.execute(
                "INSERT INTO ngw_restored_features (fid) VALUES (?)",
                (feature_id,),
            )

        result = extractor.extract_restored_features()

        self.assertEqual(len(result), 1)
        self.assertIsInstance(result[0], FeatureRestoration)
        assert isinstance(result[0], FeatureRestoration)
        self.assertEqual(result[0].fid, feature_id)
        self.assertIsNotNone(result[0].ngw_fid)

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_extract_restored_features_returns_current_fields_and_geometry(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        feature_id = self._first_feature_id(qgs_layer)
        string_attribute = self._string_attribute_index(qgs_layer)
        expected_geometry = QgsGeometry.fromWkt("Point (77 88)")

        with edit(layer.qgs_layer):
            self.assertTrue(
                layer.qgs_layer.changeAttributeValue(
                    feature_id,
                    string_attribute,
                    "restored-current-value",
                )
            )
            self.assertTrue(
                layer.qgs_layer.changeGeometry(feature_id, expected_geometry)
            )

        with ContainerReadWriteSession(container_mock.path) as cursor:
            cursor.execute(
                "DELETE FROM ngw_updated_attributes WHERE fid = ?",
                (feature_id,),
            )
            cursor.execute(
                "DELETE FROM ngw_updated_geometries WHERE fid = ?",
                (feature_id,),
            )
            cursor.execute(
                "INSERT INTO ngw_restored_features (fid) VALUES (?)",
                (feature_id,),
            )

        result = extractor.extract_restored_features()

        self.assertEqual(len(result), 1)
        field = container_mock.metadata.fields.get_with(
            attribute=string_attribute
        )
        self.assertEqual(
            result[0].fields_dict[field.ngw_id],
            "restored-current-value",
        )
        self.assertIsNot(result[0].geometry, Unset)
        assert isinstance(result[0].geometry, QgsGeometry)
        self.assertTrue(result[0].geometry.equals(expected_geometry))

    @mock_container(TestData.Points)
    def test_extract_restored_features_returns_empty_for_non_versioned(
        self, container_mock, _qgs_layer
    ) -> None:
        extractor = self._extractor(container_mock)
        result = extractor.extract_restored_features()
        self.assertEqual(result, [])

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_extract_updated_features_raises_on_invalid_time_format(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        layer = DetachedLayer(container_mock, qgs_layer)
        feature_id = self._first_feature_id(layer.qgs_layer)

        time_fields = [
            field
            for field in container_mock.metadata.fields
            if field.datatype == NgwDataType.TIME
        ]
        if len(time_fields) == 0:
            self.skipTest("Container has no TIME fields")

        time_attribute = time_fields[0].attribute
        self.assertNotEqual(time_attribute, -1)
        with edit(layer.qgs_layer):
            self.assertTrue(
                layer.qgs_layer.changeAttributeValue(
                    feature_id, time_attribute, "not-a-valid-time"
                )
            )

        with self.assertRaises(SynchronizationError) as error_context:
            extractor.extract_updated_features()
        self.assertEqual(
            error_context.exception.code,
            ErrorCode.ValueFormatError,
        )

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        descriptions={FEATURE_1: "old-description"},
        attachments=[
            AttachmentMetadata(fid=FEATURE_1, aid=201, version=11),
            AttachmentMetadata(fid=FEATURE_1, aid=202, version=12),
            AttachmentMetadata(fid=FEATURE_1, aid=203, version=13),
            AttachmentMetadata(fid=FEATURE_1, aid=204, version=14),
        ],
    )
    def test_extract_all_changes_collects_descriptions_and_attachments(
        self, container_mock, _qgs_layer
    ) -> None:
        extractor = self._extractor(container_mock)

        with ContainerReadWriteSession(container_mock.path) as cursor:
            cursor.execute(
                """
                UPDATE ngw_features_descriptions
                SET description = ?
                WHERE fid = ?
                """,
                ("new-description", self.FEATURE_1),
            )
            cursor.execute(
                """
                INSERT INTO ngw_updated_descriptions (fid, backup)
                VALUES (?, ?)
                """,
                (self.FEATURE_1, None),
            )

            cursor.execute(
                "INSERT INTO ngw_added_attachments (aid) VALUES (?)",
                (201,),
            )
            cursor.execute(
                """
                INSERT INTO ngw_updated_attachments (aid, backup)
                VALUES (?, ?)
                """,
                (202, None),
            )
            cursor.execute(
                """
                INSERT INTO ngw_removed_attachments (aid, backup)
                VALUES (?, ?)
                """,
                (203, None),
            )
            cursor.execute(
                "INSERT INTO ngw_restored_attachments (aid) VALUES (?)",
                (204,),
            )

        result = extractor.extract_all_changes()

        description_changes = [
            change for change in result if isinstance(change, DescriptionPut)
        ]
        added_attachments = [
            change
            for change in result
            if isinstance(change, AttachmentCreation)
        ]
        updated_attachments = [
            change for change in result if isinstance(change, AttachmentUpdate)
        ]
        deleted_attachments = [
            change
            for change in result
            if isinstance(change, AttachmentDeletion)
        ]
        restored_attachments = [
            change
            for change in result
            if isinstance(change, AttachmentRestoration)
        ]

        self.assertEqual(len(description_changes), 1)
        self.assertEqual(len(added_attachments), 1)
        self.assertEqual(len(updated_attachments), 1)
        self.assertEqual(len(deleted_attachments), 1)
        self.assertEqual(len(restored_attachments), 1)

        self.assertEqual(description_changes[0].fid, self.FEATURE_1)
        self.assertEqual(description_changes[0].description, "new-description")
        self.assertEqual(added_attachments[0].aid, 201)
        self.assertEqual(updated_attachments[0].aid, 202)
        self.assertEqual(deleted_attachments[0].aid, 203)
        self.assertEqual(restored_attachments[0].aid, 204)

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        descriptions={FEATURE_1: "old-description"},
        attachments=[
            AttachmentMetadata(
                fid=FEATURE_1,
                aid=201,
                ngw_aid=301,
                version=11,
                name="old-name",
                description="old-attachment-description",
                mime_type="text/plain",
                fileobj=901,
            ),
        ],
    )
    def test_extract_features_changes_excludes_extensions(
        self, container_mock, qgs_layer: QgsVectorLayer
    ) -> None:
        extractor = self._extractor(container_mock)
        detached_layer = DetachedLayer(container_mock, qgs_layer)

        attachment = detached_layer.feature_attachment(self.FEATURE_1, 201)
        assert attachment is not None

        with edit(qgs_layer):
            detached_layer.set_feature_description(
                self.FEATURE_1, "new-description"
            )
            detached_layer.update_attachment(
                AttachmentMetadata(
                    fid=self.FEATURE_1,
                    aid=201,
                    ngw_aid=301,
                    version=11,
                    name="new-name",
                    description=attachment.description,
                    mime_type=attachment.mime_type,
                    fileobj=attachment.fileobj,
                )
            )

        self.assertEqual(extractor.extract_features_changes(), [])
        self.assertEqual(len(extractor.extract_updated_descriptions()), 1)
        self.assertEqual(len(extractor.extract_updated_attachments()), 1)

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        attachments=[
            AttachmentMetadata(
                fid=FEATURE_1,
                aid=201,
                ngw_aid=301,
                version=11,
                keyname="old-key",
                name="old-name",
                description="old-description",
                mime_type="text/plain",
                fileobj=901,
            ),
        ],
    )
    def test_extract_updated_attachments_preserves_server_attachment_id(
        self, container_mock, _qgs_layer
    ) -> None:
        extractor = self._extractor(container_mock)

        with ContainerReadWriteSession(container_mock.path) as cursor:
            cursor.execute(
                """
                UPDATE ngw_features_attachments
                SET name = ?
                WHERE aid = ?
                """,
                ("new-name", 201),
            )
            cursor.execute(
                """
                INSERT INTO ngw_updated_attachments (aid, backup)
                VALUES (?, ?)
                """,
                (201, None),
            )

        result = extractor.extract_updated_attachments()

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].aid, 201)
        self.assertEqual(result[0].ngw_aid, 301)
        self.assertEqual(result[0].name, "new-name")

    @mock_container(
        TestData.Points,
        is_versioning_enabled=True,
        attachments=[
            AttachmentMetadata(
                fid=FEATURE_1,
                aid=201,
                ngw_aid=301,
                version=11,
                keyname="old-key",
                name="old-name",
                description="old-description",
                mime_type="text/plain",
                fileobj=901,
            ),
        ],
    )
    def test_extract_updated_attachments_returns_new_file_metadata(
        self, container_mock, _qgs_layer
    ) -> None:
        extractor = self._extractor(container_mock)

        with ContainerReadWriteSession(container_mock.path) as cursor:
            cursor.execute(
                """
                UPDATE ngw_features_attachments
                SET keyname = ?, fileobj = NULL, mime_type = ?
                WHERE aid = ?
                """,
                ("photo", "image/png", 201),
            )
            cursor.execute(
                """
                INSERT INTO ngw_updated_attachments (aid, backup)
                VALUES (?, ?)
                """,
                (201, None),
            )

        result = extractor.extract_updated_attachments()

        self.assertEqual(len(result), 1)
        self.assertTrue(result[0].is_file_new)
        self.assertEqual(result[0].keyname, "photo")
        self.assertIsNone(result[0].fileobj)
        self.assertEqual(result[0].mime_type, "image/png")
