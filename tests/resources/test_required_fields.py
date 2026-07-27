from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest import mock

from qgis.core import QgsFieldConstraints, QgsVectorLayer

from nextgis_connect.detached_editing.detached_layer import DetachedLayer
from nextgis_connect.detached_editing.sync.common.fetch_additional_data_task import (
    FetchAdditionalDataTask,
)
from nextgis_connect.detached_editing.utils import (
    container_metadata,
    detached_layer_uri,
)
from nextgis_connect.ngw.core import NGWVectorLayer
from nextgis_connect.ngw.core.ngw_resource_creator import ResourceCreator
from nextgis_connect.ngw.qgis.ngw_resource_model_4qgis import (
    QGISResourceJob,
)
from nextgis_connect.ngw.qgis.qgis_ngw_connection import (
    NgwServerFeature,
)
from nextgis_connect.resources.ngw_fields import NgwFields
from tests.magic_qobject_mock import MagicQObjectMock
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestRequiredFields(NgConnectTestCase):
    def _make_ngw_layer_with_required_field(self) -> NGWVectorLayer:
        layer_json = deepcopy(self.resource_json(TestData.Points))
        layer_json["feature_layer"]["fields"][0]["required"] = True
        return cast(NGWVectorLayer, self.resource(layer_json))

    def test_import_sets_required_for_not_null_fields(self) -> None:
        layer = QgsVectorLayer("Point?field=name:string", "points", "memory")
        self.assertTrue(layer.isValid())

        field_index = layer.fields().indexOf("name")
        layer.setFieldConstraint(
            field_index,
            QgsFieldConstraints.Constraint.ConstraintNotNull,
        )

        parent_resource = mock.Mock()
        parent_resource.connection.has_support_for_feature.return_value = True
        parent_resource.get_children.return_value = []

        ngw_vector_layer = mock.Mock()
        job = QGISResourceJob()

        with mock.patch.object(
            job,
            "prepareImportVectorFile",
            return_value=("/tmp/fake.gpkg", None, None),
        ), mock.patch.object(
            ResourceCreator,
            "create_vector_layer",
            return_value=ngw_vector_layer,
        ), mock.patch(
            "nextgis_connect.ngw.qgis.ngw_resource_model_4qgis.os.remove"
        ):
            job.importQgsVectorLayer(layer, parent_resource)

        parent_resource.connection.has_support_for_feature.assert_called_once_with(
            NgwServerFeature.REQUIRED_FIELDS
        )
        ngw_vector_layer.update_fields_params.assert_called_once_with(
            {"name": {"required": True}}
        )

    def test_detached_container_stores_required_metadata(self) -> None:
        ngw_layer = self._make_ngw_layer_with_required_field()
        container_path = self.create_temp_file(".gpkg")

        from nextgis_connect.detached_editing.container.container_factory import (
            DetachedContainerFactory,
        )

        DetachedContainerFactory().create_initial_container(
            ngw_layer, container_path
        )

        metadata = container_metadata(container_path)

        self.assertTrue(metadata.fields[0].is_required)

    def test_detached_layer_applies_not_null_from_metadata(self) -> None:
        ngw_layer = self._make_ngw_layer_with_required_field()
        container_path = self.create_temp_file(".gpkg")

        from nextgis_connect.detached_editing.container.container_factory import (
            DetachedContainerFactory,
        )

        DetachedContainerFactory().create_initial_container(
            ngw_layer, container_path
        )

        metadata = container_metadata(container_path)
        qgs_layer = QgsVectorLayer(
            detached_layer_uri(container_path, metadata),
            metadata.layer_name,
            "ogr",
        )
        self.assertTrue(qgs_layer.isValid())

        container_mock = MagicQObjectMock()
        container_mock.metadata = metadata
        container_mock.path = Path(container_path)

        _detached_layer = DetachedLayer(container_mock, qgs_layer)

        field_index = qgs_layer.fields().indexOf(metadata.fields[0].keyname)
        self.assertTrue(
            qgs_layer.fieldConstraints(field_index)
            & QgsFieldConstraints.Constraint.ConstraintNotNull
        )

    def test_detached_layer_updates_not_null_after_metadata_change(
        self,
    ) -> None:
        layer_without_required = cast(
            NGWVectorLayer,
            self.resource(deepcopy(self.resource_json(TestData.Points))),
        )
        layer_with_required = self._make_ngw_layer_with_required_field()
        container_path = self.create_temp_file(".gpkg")

        from nextgis_connect.detached_editing.container.container_factory import (
            DetachedContainerFactory,
        )

        DetachedContainerFactory().create_initial_container(
            layer_without_required, container_path
        )

        metadata = container_metadata(container_path)
        qgs_layer = QgsVectorLayer(
            detached_layer_uri(container_path, metadata),
            metadata.layer_name,
            "ogr",
        )
        self.assertTrue(qgs_layer.isValid())

        container_mock = MagicQObjectMock()
        container_mock.metadata = metadata
        container_mock.path = Path(container_path)

        detached_layer = DetachedLayer(container_mock, qgs_layer)
        field_index = qgs_layer.fields().indexOf(metadata.fields[0].keyname)
        self.assertFalse(
            qgs_layer.fieldConstraints(field_index)
            & QgsFieldConstraints.Constraint.ConstraintNotNull
        )

        container_mock.metadata.fields = NgwFields(layer_with_required.fields)
        detached_layer.update_required_constraints()

        self.assertTrue(
            qgs_layer.fieldConstraints(field_index)
            & QgsFieldConstraints.Constraint.ConstraintNotNull
        )

    def test_additional_structure_refresh_updates_required_metadata(
        self,
    ) -> None:
        layer_without_required = cast(
            NGWVectorLayer,
            self.resource(deepcopy(self.resource_json(TestData.Points))),
        )
        layer_with_required = self._make_ngw_layer_with_required_field()
        container_path = self.create_temp_file(".gpkg")

        from nextgis_connect.detached_editing.container.container_factory import (
            DetachedContainerFactory,
        )

        DetachedContainerFactory().create_initial_container(
            layer_without_required, container_path
        )
        self.assertFalse(
            container_metadata(container_path).fields[0].is_required
        )

        task = FetchAdditionalDataTask(container_path)
        with mock.patch.object(
            task, "_get_layer", return_value=layer_with_required
        ):
            task._FetchAdditionalDataTask__update_structure(mock.Mock())

        self.assertTrue(
            container_metadata(container_path).fields[0].is_required
        )
