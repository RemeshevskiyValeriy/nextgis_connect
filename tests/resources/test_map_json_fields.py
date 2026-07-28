from copy import deepcopy
from pathlib import Path
from unittest import mock

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsFields,
    QgsProject,
    QgsVectorFileWriter,
    QgsVectorLayer,
    QgsWkbTypes,
)

from nextgis_connect.legacy.ngw.core import NGWVectorLayer
from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    QGISResourceJob,
)
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    NgwServerFeature,
)
from nextgis_connect.legacy.ngw_resources_adder import NgwResourcesAdder
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestMapJsonFields(NgConnectTestCase):
    def _make_ngw_json_layer(self, datatype: str = "JSON") -> NGWVectorLayer:
        layer_json = deepcopy(self.resource_json(TestData.Points))
        layer_json["feature_layer"]["fields"][0]["datatype"] = datatype
        return self.resource(layer_json)

    def test_adding_json_field_sets_json_view_editor_widget(self) -> None:
        ngw_layer = self._make_ngw_json_layer()
        qgs_layer = QgsVectorLayer(
            "None?field=INTEGER:map",
            "attributes_only",
            "memory",
        )
        self.assertTrue(qgs_layer.isValid())

        adder = NgwResourcesAdder.__new__(NgwResourcesAdder)
        adder._NgwResourcesAdder__model = mock.Mock()

        adder._NgwResourcesAdder__add_edit_widgets(ngw_layer, qgs_layer)

        field_index = qgs_layer.fields().indexOf("INTEGER")
        self.assertEqual(
            qgs_layer.editorWidgetSetup(field_index).type(), "JsonView"
        )

    def test_adding_json_field_to_memory_map_layer_sets_json_view_editor_widget(
        self,
    ) -> None:
        ngw_layer = self._make_ngw_json_layer()
        qgs_layer = QgsVectorLayer(
            "None?field=INTEGER:map",
            "attributes_only",
            "memory",
        )
        self.assertTrue(qgs_layer.isValid())

        adder = NgwResourcesAdder.__new__(NgwResourcesAdder)
        adder._NgwResourcesAdder__model = mock.Mock()

        adder._NgwResourcesAdder__add_edit_widgets(ngw_layer, qgs_layer)

        field_index = qgs_layer.fields().indexOf("INTEGER")
        self.assertEqual(
            qgs_layer.editorWidgetSetup(field_index).type(), "JsonView"
        )

    def test_upload_sets_ngw_json_datatype_for_memory_map_field(self) -> None:
        layer = QgsVectorLayer("None?field=payload:map", "attrs", "memory")
        self.assertTrue(layer.isValid())

        parent_resource = mock.Mock()
        parent_resource.connection.has_support_for_feature.side_effect = (
            lambda feature: feature == NgwServerFeature.JSON_TYPE
        )
        parent_resource.get_children.return_value = []

        ngw_vector_layer = mock.Mock()
        job = QGISResourceJob()

        with mock.patch.object(
            job,
            "prepareImportVectorFile",
            return_value=("/tmp/fake.gpkg", None, None),
        ), mock.patch(
            "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis.ResourceCreator.create_vector_layer",
            return_value=ngw_vector_layer,
        ), mock.patch(
            "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis.os.remove"
        ):
            job.importQgsVectorLayer(layer, parent_resource)

        ngw_vector_layer.update_fields_params.assert_called_once_with(
            {"payload": {"datatype": "JSON"}}
        )

    def test_json_field_is_compatible_with_gpkg_json_field(self) -> None:
        ngw_layer = self._make_ngw_json_layer()
        gpkg_path = Path(self.create_temp_file(".gpkg"))
        gpkg_path.unlink(missing_ok=True)

        fields = QgsFields()
        fields.append(ngw_layer.fields[0].to_qgs_field())

        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = "test"
        options.fileEncoding = "UTF-8"
        options.layerOptions = [
            *QgsVectorFileWriter.defaultDatasetOptions("GPKG"),
            "FID=fid",
        ]

        writer = QgsVectorFileWriter.create(
            fileName=str(gpkg_path),
            fields=fields,
            geometryType=QgsWkbTypes.Type.NoGeometry,
            transformContext=QgsProject.instance().transformContext(),
            srs=QgsCoordinateReferenceSystem(),
            options=options,
        )
        feature = QgsFeature(fields)
        feature.setAttribute("INTEGER", {"a": "b"})
        writer.addFeature(feature)
        del writer

        layer = QgsVectorLayer(f"{gpkg_path}|layername=test", "", "ogr")
        self.assertTrue(layer.isValid())

        field_index = layer.fields().indexOf("INTEGER")
        qgs_field = layer.fields().at(field_index)

        self.assertEqual(qgs_field.typeName(), "JSON")
        self.assertTrue(ngw_layer.fields[0].is_compatible(qgs_field))
