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

from pathlib import Path

from osgeo import gdal
from qgis.core import Qgis

from nextgis_connect.platform.qgis.compat import (
    DataType,
    QgsRasterFileWriter,
)


def test_data_type_from_qgis_accepts_qgis_enum_value(qgis_app) -> None:
    del qgis_app

    data_type = DataType.from_qgis(Qgis.DataType.Float32)

    assert data_type == DataType.Float32
    assert data_type.to_gdal() == int(gdal.GDT_Float32)


def test_data_type_from_qgis_returns_unknown_for_unknown_value(
    qgis_app,
) -> None:
    del qgis_app

    assert DataType.from_qgis(999999) == DataType.UnknownDataType
    assert DataType.from_qgis(object()) == DataType.UnknownDataType


def test_raster_file_writer_has_current_creation_options_api(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    writer = QgsRasterFileWriter(str(tmp_path / "compat.tif"))

    writer.setCreationOptions(["BIGTIFF=YES"])

    assert writer.creationOptions() == ["BIGTIFF=YES"]
