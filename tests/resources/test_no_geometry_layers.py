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

import urllib.parse
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from typing import cast
from unittest import mock

from qgis.core import QgsFeature, QgsField, QgsVectorLayer

from nextgis_connect.legacy.detached_editing.container.container_factory import (
    DetachedContainerFactory,
)
from nextgis_connect.legacy.detached_editing.utils import (
    container_metadata,
    detached_layer_uri,
    make_connection,
)
from nextgis_connect.legacy.ngw.core import NGWVectorLayer
from nextgis_connect.legacy.ngw.core.vector_layer_export import (
    VectorLayerExportParams,
)
from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    QGISResourceJob,
)
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    NgwServerFeature,
)
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job_error import (
    JobError,
)
from nextgis_connect.platform.qgis.compat import (
    FieldType,
    GeometryType,
    LayerType,
)
from nextgis_connect.platform.qgis.errors import ContainerError, NgwError
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestNoGeometryLayers(NgConnectTestCase):
    def _make_ngw_no_geometry_layer(
        self,
        *,
        is_versioning_enabled: bool = False,
    ) -> NGWVectorLayer:
        layer_json = deepcopy(self.resource_json(TestData.Points))
        layer_json["feature_layer"]["versioning"] = {
            "enabled": is_versioning_enabled,
        }
        layer_json["vector_layer"] = {
            "srs": None,
            "geometry_type": "NONE",
        }
        return cast(NGWVectorLayer, self.resource(layer_json))

    def test_export_filter_accepts_layer_without_geometry(self) -> None:
        layer = mock.Mock(spec=QgsVectorLayer)
        layer.type.return_value = LayerType.Vector
        layer.geometryType.return_value = GeometryType.Null

        job = QGISResourceJob()

        self.assertEqual(job.isSuitableLayer(layer), job.SUITABLE_LAYER)

    def test_ngw_vector_layer_export_omits_srs_without_geometry(self) -> None:
        layer = self._make_ngw_no_geometry_layer()
        export_path = self.create_temp_file(".gpkg")

        layer.export(str(export_path))

        connection = layer.res_factory.connection
        connection.download.assert_called_once()
        export_url = connection.download.call_args.args[0]
        query = urllib.parse.parse_qs(
            urllib.parse.urlsplit(export_url).query,
            keep_blank_values=True,
        )
        self.assertNotIn("srs", query)
        self.assertEqual(query["format"], ["GPKG"])
        self.assertEqual(query["fid"], [""])
        self.assertEqual(query["zipped"], ["false"])

    def test_vector_layer_export_query_omits_srs_without_geometry(
        self,
    ) -> None:
        export_query = VectorLayerExportParams(
            has_geometry=False,
            srs_id=3857,
        ).to_query()
        query = urllib.parse.parse_qs(
            export_query,
            keep_blank_values=True,
        )

        self.assertNotIn("srs", query)
        self.assertEqual(query["format"], ["GPKG"])
        self.assertEqual(query["fid"], [""])
        self.assertEqual(query["zipped"], ["false"])

    def test_vector_layer_export_query_omits_zero_srs(self) -> None:
        export_query = VectorLayerExportParams(
            fid_field="fid",
            srs_id=0,
        ).to_query()
        query = urllib.parse.parse_qs(
            export_query,
            keep_blank_values=True,
        )

        self.assertNotIn("srs", query)
        self.assertEqual(query["format"], ["GPKG"])
        self.assertEqual(query["fid"], ["fid"])
        self.assertEqual(query["zipped"], ["false"])

    def test_no_geometry_layer_rejects_qml_style_upload(self) -> None:
        layer = self._make_ngw_no_geometry_layer()
        connection = layer.res_factory.connection

        with self.assertRaises(NgwError):
            layer.create_qml_style(
                "/tmp/style.qml",
                lambda *_args: None,
            )

        connection.upload_file.assert_not_called()

    def test_add_style_skips_layer_without_geometry(self) -> None:
        ngw_layer = self._make_ngw_no_geometry_layer()
        qgis_layer = QgsVectorLayer("None", "attributes_only", "memory")
        self.assertTrue(qgis_layer.isValid())

        style_manager = qgis_layer.styleManager()
        self.assertIsNotNone(style_manager)
        assert style_manager is not None

        job = QGISResourceJob()

        ngw_style = job.addStyle(
            ngw_layer,
            qgis_layer,
            style_manager.currentStyle(),
        )

        self.assertIsNone(ngw_style)
        ngw_layer.res_factory.connection.upload_file.assert_not_called()

    def test_export_without_geometry_requires_supported_ngw_version(
        self,
    ) -> None:
        layer = QgsVectorLayer("None", "attributes_only", "memory")
        self.assertTrue(layer.isValid())

        parent_resource = mock.Mock()
        parent_resource.connection.has_support_for_feature.return_value = False
        parent_resource.get_children.return_value = []

        job = QGISResourceJob()

        with self.assertRaises(JobError) as error_context:
            job.importQgsVectorLayer(layer, parent_resource)

        self.assertIn("5.5.0", str(error_context.exception))
        parent_resource.connection.has_support_for_feature.assert_called_once_with(
            NgwServerFeature.NO_GEOMETRY_LAYERS
        )

    def test_prepare_as_gpkg_keeps_layer_without_geometry(self) -> None:
        layer = QgsVectorLayer("None", "attributes_only", "memory")
        self.assertTrue(layer.isValid())

        provider = layer.dataProvider()
        self.assertIsNotNone(provider)
        assert provider is not None

        self.assertTrue(
            provider.addAttributes(
                [
                    QgsField("name", FieldType.QString),
                    QgsField("value", FieldType.Int),
                ]
            )
        )
        layer.updateFields()

        feature = QgsFeature(layer.fields())
        feature.setAttribute("name", "row")
        feature.setAttribute("value", 1)
        self.assertTrue(provider.addFeature(feature))

        job = QGISResourceJob()
        gpkg_path, old_fid_name = job.prepareAsGPKG(layer)

        try:
            self.assertIsNone(old_fid_name)

            exported_layer = QgsVectorLayer(
                f"{gpkg_path}|layername={layer.name()}", "", "ogr"
            )
            self.assertTrue(exported_layer.isValid())
            self.assertEqual(exported_layer.geometryType(), GeometryType.Null)
            self.assertEqual(exported_layer.featureCount(), 1)

            exported_feature = next(exported_layer.getFeatures())
            self.assertEqual(exported_feature["name"], "row")
            self.assertEqual(exported_feature["value"], 1)
        finally:
            Path(gpkg_path).unlink(missing_ok=True)

    def test_detached_container_supports_ngw_layer_without_geometry(
        self,
    ) -> None:
        ngw_layer = self._make_ngw_no_geometry_layer()
        ngw_layer.res_factory.connection.has_support_for_feature.return_value = True

        container_path = self.create_temp_file(".gpkg")

        DetachedContainerFactory().create_initial_container(
            ngw_layer, container_path
        )

        metadata = container_metadata(container_path)
        self.assertEqual(metadata.geometry_name, "NONE")
        self.assertIsNone(metadata.geom_field)
        self.assertEqual(
            metadata.table_name, f"vector_layer_{ngw_layer.resource_id}"
        )
        ngw_layer.connection.get.assert_not_called()

        with closing(make_connection(container_path)) as connection, closing(
            connection.cursor()
        ) as cursor:
            cursor.execute(
                """
                SELECT min_x, min_y, max_x, max_y
                FROM gpkg_contents
                WHERE table_name = ?
                """,
                (metadata.table_name,),
            )
            self.assertEqual(cursor.fetchone(), (None, None, None, None))

        layer = QgsVectorLayer(detached_layer_uri(container_path), "", "ogr")
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.geometryType(), GeometryType.Null)

    def test_detached_container_without_geometry_requires_supported_ngw_version(
        self,
    ) -> None:
        ngw_layer = self._make_ngw_no_geometry_layer()
        ngw_layer.res_factory.connection.has_support_for_feature.return_value = False

        container_path = self.create_temp_file(".gpkg")

        with self.assertRaises(ContainerError) as error_context:
            DetachedContainerFactory().create_initial_container(
                ngw_layer, container_path
            )

        self.assertEqual(
            error_context.exception.code,
            error_context.exception.code.ContainerCreationError,
        )
        self.assertIn("5.5.0", str(error_context.exception))
        ngw_layer.res_factory.connection.has_support_for_feature.assert_called_once_with(
            NgwServerFeature.NO_GEOMETRY_LAYERS
        )

    def test_detached_container_without_geometry_with_versioning_requires_dev8(
        self,
    ) -> None:
        ngw_layer = self._make_ngw_no_geometry_layer(
            is_versioning_enabled=True
        )
        ngw_layer.res_factory.connection.has_support_for_feature.return_value = False

        container_path = self.create_temp_file(".gpkg")

        with self.assertRaises(ContainerError) as error_context:
            DetachedContainerFactory().create_initial_container(
                ngw_layer, container_path
            )

        self.assertEqual(
            error_context.exception.code,
            error_context.exception.code.ContainerCreationError,
        )
        self.assertIn("5.5.0.dev8", str(error_context.exception))
        ngw_layer.res_factory.connection.has_support_for_feature.assert_called_once_with(
            NgwServerFeature.NO_GEOMETRY_LAYER_VERSIONING
        )
