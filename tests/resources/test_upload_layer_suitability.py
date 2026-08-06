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

from unittest import mock

import pytest
from qgis.core import QgsMapLayer, QgsRasterLayer

from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    NGWUpdateRasterLayer,
    QGISResourceJob,
)
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job_error import (
    JobError,
)
from nextgis_connect.platform.qgis.compat import LayerType


def test_vector_tile_layer_is_not_suitable_for_upload(qgis_app) -> None:
    del qgis_app
    layer = mock.Mock(spec=QgsMapLayer)
    layer.type.return_value = LayerType.VectorTile
    layer.source.return_value = ""
    job = QGISResourceJob()

    assert job.isSuitableLayer(layer) == job.SUITABLE_LAYER_UNSUPPORTED


def test_mbtiles_raster_layer_is_suitable_for_upload(qgis_app) -> None:
    del qgis_app
    layer = mock.Mock(spec=QgsRasterLayer)
    layer.type.return_value = LayerType.Raster
    layer.source.return_value = "/tmp/example.MBTILES|layername=tiles"
    job = QGISResourceJob()

    assert job.isSuitableLayer(layer) == job.SUITABLE_LAYER


def test_unsupported_layer_is_skipped_before_parent_resource_update(
    qgis_app,
) -> None:
    del qgis_app
    layer = mock.Mock(spec=QgsMapLayer)
    layer.type.return_value = LayerType.VectorTile
    layer.source.return_value = ""
    parent_resource = mock.Mock()
    job = QGISResourceJob()

    assert job.importQGISMapLayer(layer, parent_resource) == []
    parent_resource.update.assert_not_called()


def test_mbtiles_raster_overwrite_is_rejected_before_file_preparation(
    qgis_app,
) -> None:
    del qgis_app
    layer = mock.Mock(spec=QgsRasterLayer)
    layer.type.return_value = LayerType.Raster
    layer.source.return_value = "/tmp/example.mbtiles"
    layer.name.return_value = "tiles"
    job = NGWUpdateRasterLayer(mock.Mock(), layer)
    job.prepareImportRasterFile = mock.Mock()

    with pytest.raises(JobError, match="not supported for upload"):
        job._do()

    job.prepareImportRasterFile.assert_not_called()


def test_mbtiles_raster_upload_creates_tileset(qgis_app, tmp_path) -> None:
    del qgis_app
    mbtiles_path = tmp_path / "example.mbtiles"
    mbtiles_path.touch()

    layer = mock.Mock(spec=QgsRasterLayer)
    layer.name.return_value = "tiles"
    layer.source.return_value = f"{mbtiles_path}|layername=tiles"
    layer.providerType.return_value = "gdal"

    parent_resource = mock.Mock()
    parent_resource.get_children.return_value = []

    created_tileset = mock.Mock()
    job = QGISResourceJob()

    with mock.patch(
        "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis"
        ".ResourceCreator.create_tileset",
        return_value=created_tileset,
    ) as create_tileset:
        result = job.importQgsTilesetLayer(layer, parent_resource)

    assert result == created_tileset
    create_tileset.assert_called_once()
    assert create_tileset.call_args.args[:3] == (
        parent_resource,
        str(mbtiles_path),
        "tiles",
    )


def test_wms_mbtiles_raster_upload_uses_local_file_path(
    qgis_app,
    tmp_path,
) -> None:
    del qgis_app
    mbtiles_path = tmp_path / "example.mbtiles"
    mbtiles_path.touch()

    layer = mock.Mock(spec=QgsRasterLayer)
    layer.name.return_value = "tiles"
    layer.source.return_value = f"url={mbtiles_path.as_uri()}&type=mbtiles"
    layer.providerType.return_value = "wms"

    parent_resource = mock.Mock()
    parent_resource.get_children.return_value = []

    created_tileset = mock.Mock()
    job = QGISResourceJob()

    with mock.patch(
        "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis"
        ".ResourceCreator.create_tileset",
        return_value=created_tileset,
    ) as create_tileset:
        result = job.importQgsTilesetLayer(layer, parent_resource)

    assert result == created_tileset
    create_tileset.assert_called_once()
    assert create_tileset.call_args.args[:3] == (
        parent_resource,
        str(mbtiles_path),
        "tiles",
    )
