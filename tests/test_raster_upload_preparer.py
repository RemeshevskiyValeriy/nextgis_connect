import time
import uuid
import zipfile
from pathlib import Path
from typing import Set

from osgeo import gdal
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsProviderRegistry,
    QgsRasterLayer,
)

from nextgis_connect.legacy.ngw.core.ngw_raster_layer import NGWRasterLayer
from nextgis_connect.legacy.ngw.core.ngw_resource import NGWResource
from nextgis_connect.legacy.ngw.core.ngw_resource_creator import (
    ResourceCreator,
)
from nextgis_connect.legacy.ngw.core.ngw_resource_factory import (
    NGWResourceFactory,
)
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.legacy.ngw.qgis.raster_upload_preparer import (
    AUX_XML_SUFFIX,
    GEOTIFF_SUFFIX,
    PreparedRasterFile,
    RasterUploadPreparer,
)
from nextgis_connect.platform.filesystem import rm
from tests.ng_connect_testcase import NgConnectTestCase, TestConnection

LOCAL_PROJ = (
    "+proj=tmerc +lat_0=0 +lon_0=37 +k=1 +x_0=500000 +y_0=0 "
    "+datum=WGS84 +units=m +no_defs"
)

gdal.UseExceptions()


class MisconvertingRasterUploadPreparer(RasterUploadPreparer):
    def _convert_to_geotiff(self, layer: QgsRasterLayer) -> Path:
        output_path = self._temporary_path(GEOTIFF_SUFFIX)

        source_dataset = gdal.Open(layer.source())
        assert source_dataset is not None

        driver = gdal.GetDriverByName("GTiff")
        assert driver is not None

        output_dataset = driver.Create(
            str(output_path),
            source_dataset.RasterXSize,
            source_dataset.RasterYSize,
            1,
            gdal.GDT_UInt16,
        )
        assert output_dataset is not None

        output_dataset.SetProjection(source_dataset.GetProjection())
        output_dataset.SetGeoTransform(source_dataset.GetGeoTransform())
        output_dataset.GetRasterBand(1).Fill(11)

        output_dataset = None
        source_dataset = None

        self._fix_converted_data_type_if_needed(layer, output_path)
        return output_path


class MissingCrsRasterUploadPreparer(RasterUploadPreparer):
    def _convert_to_geotiff(self, layer: QgsRasterLayer) -> Path:
        output_path = self._temporary_path(GEOTIFF_SUFFIX)

        source_dataset = gdal.Open(layer.source())
        assert source_dataset is not None

        driver = gdal.GetDriverByName("GTiff")
        assert driver is not None

        output_dataset = driver.Create(
            str(output_path),
            source_dataset.RasterXSize,
            source_dataset.RasterYSize,
            1,
            source_dataset.GetRasterBand(1).DataType,
        )
        assert output_dataset is not None

        output_dataset.SetGeoTransform(source_dataset.GetGeoTransform())
        output_dataset.GetRasterBand(1).Fill(13)

        output_dataset = None
        source_dataset = None

        self._restore_exported_crs_if_needed(layer, output_path)
        return output_path


class DownloadOnlyRasterUploadPreparer(RasterUploadPreparer):
    def _convert_to_geotiff(self, layer: QgsRasterLayer) -> Path:
        raise AssertionError("GeoTIFF export should not be used")


class ProjOnlyCrs:
    def isValid(self) -> bool:
        return True

    def toProj(self) -> str:
        return LOCAL_PROJ

    def toWkt(self) -> str:
        return ""


class ProjOnlyLayer:
    def crs(self) -> ProjOnlyCrs:
        return ProjOnlyCrs()

    def name(self) -> str:
        return "proj-only-layer"


class TestRasterUploadPreparer(NgConnectTestCase):
    @staticmethod
    def _epsg_3857() -> QgsCoordinateReferenceSystem:
        return QgsCoordinateReferenceSystem.fromEpsgId(3857)

    @staticmethod
    def _local_crs() -> QgsCoordinateReferenceSystem:
        crs = QgsCoordinateReferenceSystem.fromProj(LOCAL_PROJ)
        assert crs.isValid()
        assert crs.postgisSrid() == 0
        return crs

    def _create_geotiff(
        self,
        raster_path: Path,
        *,
        crs: QgsCoordinateReferenceSystem,
        data_type: int = gdal.GDT_Byte,
    ) -> None:
        driver = gdal.GetDriverByName("GTiff")
        assert driver is not None

        dataset = driver.Create(str(raster_path), 4, 4, 1, data_type)
        assert dataset is not None

        dataset.SetProjection(crs.toWkt())
        dataset.SetGeoTransform([0, 1, 0, 0, 0, -1])
        dataset.GetRasterBand(1).Fill(7)
        dataset = None

    def _create_unreferenced_geotiff(
        self,
        raster_path: Path,
        *,
        data_type: int = gdal.GDT_Byte,
    ) -> None:
        driver = gdal.GetDriverByName("GTiff")
        assert driver is not None

        dataset = driver.Create(str(raster_path), 4, 4, 1, data_type)
        assert dataset is not None

        dataset.GetRasterBand(1).Fill(7)
        dataset = None

    def _create_raster(
        self,
        raster_path: Path,
        *,
        crs: QgsCoordinateReferenceSystem,
        format_name: str = "GTiff",
        data_type: int = gdal.GDT_Byte,
    ) -> None:
        if format_name == "GTiff":
            self._create_geotiff(raster_path, crs=crs, data_type=data_type)
            return

        source_path = raster_path.with_name(f"{raster_path.stem}_source.tif")
        self._create_geotiff(source_path, crs=crs, data_type=data_type)

        translated = gdal.Translate(
            str(raster_path),
            str(source_path),
            options=gdal.TranslateOptions(format=format_name),
        )
        assert translated is not None
        translated = None

    def _raster_layer(self, raster_path: Path) -> QgsRasterLayer:
        layer = QgsRasterLayer(str(raster_path), raster_path.stem, "gdal")
        self.assertTrue(layer.isValid())
        return layer

    def _aux_xml_path(self, raster_path: Path) -> Path:
        return raster_path.with_name(f"{raster_path.name}{AUX_XML_SUFFIX}")

    def _archive_names(self, archive_path: Path) -> Set[str]:
        with zipfile.ZipFile(str(archive_path)) as archive:
            return set(archive.namelist())

    def _read_archive_text(self, archive_path: Path, member_name: str) -> str:
        with zipfile.ZipFile(str(archive_path)) as archive:
            return archive.read(member_name).decode("utf-8")

    def _register_prepared_cleanup(
        self, prepared_file: PreparedRasterFile
    ) -> None:
        if prepared_file.is_temporary:
            self.addCleanup(rm, prepared_file.upload_path)

    def _sandbox_factory(self) -> NGWResourceFactory:
        connection_id = self.connection_id(TestConnection.SandboxGuest)
        return NGWResourceFactory(QgsNgwConnection(connection_id))

    def _create_sandbox_group(self) -> NGWResource:
        factory = self._sandbox_factory()
        root_resource = factory.get_root_resource()
        group_name = f"test-raster-upload-{uuid.uuid4().hex[:8]}"
        group_resource = ResourceCreator.create_group(
            root_resource, group_name
        )
        self.addCleanup(NGWResource.delete_resource, group_resource)
        return group_resource

    def _upload_raster_resource(
        self,
        parent_resource: NGWResource,
        raster_path: Path,
        display_name: str,
        *,
        upload_as_cog: bool,
    ) -> NGWRasterLayer:
        connection = parent_resource.res_factory.connection
        upload_desc = connection.tus_upload_file(
            str(raster_path), lambda *_args: None
        )
        result = connection.post(
            parent_resource.get_api_collection_url(),
            params={
                "resource": {
                    "cls": NGWRasterLayer.type_id,
                    "parent": {"id": parent_resource.resource_id},
                    "display_name": display_name,
                },
                "raster_layer": {
                    "srs": {"id": 3857},
                    "source": upload_desc,
                    "cog": upload_as_cog,
                },
            },
            is_lunkwill=True,
        )
        return parent_resource.res_factory.get_resource(result["id"])

    def _vsicurl_layer(
        self, raster_resource: NGWRasterLayer
    ) -> QgsRasterLayer:
        resource_uri = QgsProviderRegistry.instance().encodeUri(
            "gdal",
            {
                "path": (
                    f"/vsicurl/{raster_resource.get_absolute_api_url()}/cog"
                )
            },
        )

        for _ in range(5):
            layer = QgsRasterLayer(
                resource_uri, raster_resource.display_name, "gdal"
            )
            if layer.isValid() and layer.crs().isValid():
                layer.setCustomProperty(
                    "ngw_connection_id", raster_resource.connection_id
                )
                layer.setCustomProperty(
                    "ngw_resource_id", raster_resource.resource_id
                )
                return layer

            time.sleep(1)

        self.fail("Failed to open sandbox raster as vsicurl COG")

    def test_prepare_keeps_uploadable_geotiff_without_sidecars(self) -> None:
        work_dir = self.create_temp_dir("-raster-keep")
        raster_path = work_dir / "simple.tif"
        self._create_raster(raster_path, crs=self._epsg_3857())

        prepared = RasterUploadPreparer().prepare(
            self._raster_layer(raster_path)
        )

        self.assertEqual(prepared.upload_path, raster_path)
        self.assertFalse(prepared.is_temporary)
        self.assertFalse(prepared.is_archive)

    def test_prepare_archives_uploadable_geotiff_with_sidecars(self) -> None:
        work_dir = self.create_temp_dir("-raster-sidecar")
        raster_path = work_dir / "with_sidecar.tif"
        self._create_raster(raster_path, crs=self._epsg_3857())

        sidecar_path = raster_path.with_suffix(".tfw")
        sidecar_path.write_text("1\n0\n0\n-1\n0.5\n-0.5\n")

        prepared = RasterUploadPreparer().prepare(
            self._raster_layer(raster_path)
        )
        self._register_prepared_cleanup(prepared)

        self.assertTrue(prepared.is_temporary)
        self.assertTrue(prepared.is_archive)
        self.assertEqual(
            self._archive_names(prepared.upload_path),
            {raster_path.name, sidecar_path.name},
        )

    def test_prepare_archives_local_crs_geotiff_with_aux_xml(self) -> None:
        work_dir = self.create_temp_dir("-raster-local-crs")
        raster_path = work_dir / "local_crs.tif"
        self._create_raster(raster_path, crs=self._local_crs())

        prepared = RasterUploadPreparer().prepare(
            self._raster_layer(raster_path)
        )
        self._register_prepared_cleanup(prepared)

        aux_name = self._aux_xml_path(raster_path).name
        self.assertTrue(prepared.is_temporary)
        self.assertTrue(prepared.is_archive)
        self.assertEqual(
            self._archive_names(prepared.upload_path),
            {raster_path.name, aux_name},
        )
        archive_aux_text = self._read_archive_text(
            prepared.upload_path, aux_name
        )
        self.assertIn("<SRS", archive_aux_text)
        self.assertIn("<GeoTransform>", archive_aux_text)

    def test_prepare_archives_png_with_pgw_and_aux_xml(self) -> None:
        work_dir = self.create_temp_dir("-raster-png-sidecar")
        source_path = work_dir / "png_source.tif"
        raster_path = work_dir / "with_world.png"
        self._create_unreferenced_geotiff(source_path)

        translated = gdal.Translate(
            str(raster_path),
            str(source_path),
            options=gdal.TranslateOptions(format="PNG"),
        )
        assert translated is not None
        translated = None

        sidecar_path = raster_path.with_suffix(".pgw")
        sidecar_path.write_text("1\n0\n0\n-1\n0.5\n-0.5\n")

        layer = self._raster_layer(raster_path)
        layer.setCrs(self._epsg_3857(), False)

        prepared = RasterUploadPreparer().prepare(layer)
        self._register_prepared_cleanup(prepared)

        aux_name = self._aux_xml_path(raster_path).name
        self.assertTrue(prepared.is_temporary)
        self.assertTrue(prepared.is_archive)
        self.assertEqual(
            self._archive_names(prepared.upload_path),
            {raster_path.name, sidecar_path.name, aux_name},
        )
        self.assertIn(
            "<SRS",
            self._read_archive_text(prepared.upload_path, aux_name),
        )

    def test_collect_sidecar_files_covers_jpg_and_png_variants(self) -> None:
        work_dir = self.create_temp_dir("-raster-known-sidecars")
        preparer = RasterUploadPreparer()

        cases = (
            (
                "image.jpg",
                {
                    "image.jgw",
                    "image.jpgw",
                    "image.wld",
                    "image.jpg.aux.xml",
                },
            ),
            (
                "image.jpeg",
                {
                    "image.jgw",
                    "image.jpegw",
                    "image.wld",
                    "image.jpeg.aux.xml",
                },
            ),
            (
                "image.png",
                {
                    "image.pgw",
                    "image.pngw",
                    "image.wld",
                    "image.png.aux.xml",
                },
            ),
        )

        for raster_name, sidecar_names in cases:
            raster_path = work_dir / raster_name
            raster_path.write_text("x")

            for sidecar_name in sidecar_names:
                (work_dir / sidecar_name).write_text("x")

            collected_names = {
                sidecar_path.name
                for sidecar_path in preparer._collect_sidecar_files(
                    raster_path
                )
            }
            self.assertEqual(collected_names, sidecar_names)

            raster_path.unlink()
            for sidecar_name in sidecar_names:
                (work_dir / sidecar_name).unlink()

    def test_prepare_updates_existing_aux_xml_without_touching_source(
        self,
    ) -> None:
        work_dir = self.create_temp_dir("-raster-update-aux")
        source_path = work_dir / "jpeg_source.tif"
        raster_path = work_dir / "with_aux.jpg"
        self._create_unreferenced_geotiff(source_path)

        translated = gdal.Translate(
            str(raster_path),
            str(source_path),
            options=gdal.TranslateOptions(format="JPEG"),
        )
        assert translated is not None
        translated = None

        world_path = raster_path.with_suffix(".jgw")
        world_path.write_text("1\n0\n0\n-1\n0.5\n-0.5\n")

        source_aux_path = self._aux_xml_path(raster_path)
        source_aux_text = (
            "<PAMDataset>\n"
            f"  <SRS>{QgsCoordinateReferenceSystem.fromEpsgId(4326).toWkt()}</SRS>\n"
            "</PAMDataset>\n"
        )
        source_aux_path.write_text(source_aux_text)

        layer = self._raster_layer(raster_path)
        self.assertEqual(layer.crs().postgisSrid(), 4326)
        layer.setCrs(self._epsg_3857(), False)
        source_aux_text_before_prepare = source_aux_path.read_text()

        prepared = RasterUploadPreparer().prepare(layer)
        self._register_prepared_cleanup(prepared)

        self.assertTrue(prepared.is_temporary)
        self.assertTrue(prepared.is_archive)
        self.assertEqual(
            self._archive_names(prepared.upload_path),
            {raster_path.name, world_path.name, source_aux_path.name},
        )
        self.assertEqual(
            source_aux_path.read_text(), source_aux_text_before_prepare
        )

        archive_aux_text = self._read_archive_text(
            prepared.upload_path,
            source_aux_path.name,
        )
        self.assertNotEqual(archive_aux_text, source_aux_text_before_prepare)
        self.assertIn("3857", archive_aux_text)

        extracted_dir = self.create_temp_dir("-raster-update-aux-extracted")
        with zipfile.ZipFile(str(prepared.upload_path)) as archive:
            archive.extractall(str(extracted_dir))

        extracted_layer = self._raster_layer(extracted_dir / raster_path.name)
        self.assertEqual(extracted_layer.crs().postgisSrid(), 3857)

    def test_unlink_if_exists_accepts_sequence(self) -> None:
        work_dir = self.create_temp_dir("-raster-unlink-sequence")
        preparer = RasterUploadPreparer()

        first_path = work_dir / "first.tmp"
        second_path = work_dir / "second.tmp"
        missing_path = work_dir / "missing.tmp"

        first_path.write_text("1")
        second_path.write_text("2")

        preparer._unlink_if_exists([first_path, second_path, missing_path])

        self.assertFalse(first_path.exists())
        self.assertFalse(second_path.exists())
        self.assertFalse(missing_path.exists())

    def test_prepare_converts_gpkg_raster_to_geotiff_with_crs(self) -> None:
        work_dir = self.create_temp_dir("-raster-convert")
        raster_path = work_dir / "convert_me.gpkg"
        self._create_raster(
            raster_path, crs=self._epsg_3857(), format_name="GPKG"
        )

        prepared = RasterUploadPreparer().prepare(
            self._raster_layer(raster_path)
        )
        self._register_prepared_cleanup(prepared)

        self.assertTrue(prepared.is_temporary)
        self.assertFalse(prepared.is_archive)
        self.assertEqual(prepared.upload_path.suffix, GEOTIFF_SUFFIX)

        prepared_layer = self._raster_layer(prepared.upload_path)
        self.assertEqual(prepared_layer.crs().postgisSrid(), 3857)

        dataset = gdal.Open(str(prepared.upload_path))
        assert dataset is not None
        self.assertTrue(bool(dataset.GetProjection()))
        self.assertEqual(dataset.GetRasterBand(1).GetOverviewCount(), 0)
        self.assertFalse(
            any(
                file_path.lower().endswith(".ovr")
                for file_path in (dataset.GetFileList() or [])
            )
        )
        dataset = None

    def test_prepare_restores_data_type_for_local_crs_conversion(self) -> None:
        work_dir = self.create_temp_dir("-raster-fix-type")
        raster_path = work_dir / "fix_type.gpkg"
        self._create_raster(
            raster_path, crs=self._local_crs(), format_name="GPKG"
        )

        prepared = MisconvertingRasterUploadPreparer().prepare(
            self._raster_layer(raster_path)
        )
        self._register_prepared_cleanup(prepared)

        self.assertTrue(prepared.is_temporary)
        self.assertTrue(prepared.is_archive)

        archive_names = self._archive_names(prepared.upload_path)
        tif_names = [name for name in archive_names if name.endswith(".tif")]
        aux_names = [
            name for name in archive_names if name.endswith(AUX_XML_SUFFIX)
        ]

        self.assertEqual(len(tif_names), 1)
        self.assertEqual(len(aux_names), 1)
        self.assertIn(
            "<SRS",
            self._read_archive_text(prepared.upload_path, aux_names[0]),
        )

        with zipfile.ZipFile(str(prepared.upload_path)) as archive:
            archive.extract(tif_names[0], str(work_dir))

        extracted_raster_path = work_dir / tif_names[0]
        extracted_layer = self._raster_layer(extracted_raster_path)
        self.assertEqual(extracted_layer.crs().postgisSrid(), 0)

        dataset = gdal.Open(str(extracted_raster_path))
        assert dataset is not None
        self.assertEqual(dataset.GetRasterBand(1).DataType, gdal.GDT_Byte)
        self.assertTrue(bool(dataset.GetProjection()))
        dataset = None

    def test_prepare_restores_missing_crs_for_converted_raster(self) -> None:
        work_dir = self.create_temp_dir("-raster-fix-crs")
        raster_path = work_dir / "fix_crs.gpkg"
        self._create_raster(
            raster_path, crs=self._epsg_3857(), format_name="GPKG"
        )

        prepared = MissingCrsRasterUploadPreparer().prepare(
            self._raster_layer(raster_path)
        )
        self._register_prepared_cleanup(prepared)

        self.assertTrue(prepared.is_temporary)
        self.assertFalse(prepared.is_archive)
        self.assertEqual(prepared.upload_path.suffix, GEOTIFF_SUFFIX)

        prepared_layer = self._raster_layer(prepared.upload_path)
        self.assertEqual(prepared_layer.crs().postgisSrid(), 3857)

        dataset = gdal.Open(str(prepared.upload_path))
        assert dataset is not None
        self.assertTrue(bool(dataset.GetProjection()))
        dataset = None

    def test_restore_exported_crs_uses_proj_when_wkt_is_missing(self) -> None:
        work_dir = self.create_temp_dir("-raster-proj-only-crs")
        raster_path = work_dir / "proj_only.tif"

        driver = gdal.GetDriverByName("GTiff")
        assert driver is not None

        dataset = driver.Create(str(raster_path), 4, 4, 1, gdal.GDT_Byte)
        assert dataset is not None

        dataset.SetGeoTransform([0, 1, 0, 0, 0, -1])
        dataset.GetRasterBand(1).Fill(5)
        dataset = None

        RasterUploadPreparer()._restore_exported_crs_if_needed(
            ProjOnlyLayer(), raster_path
        )

        restored_layer = self._raster_layer(raster_path)
        self.assertTrue(restored_layer.crs().isValid())

        restored_dataset = gdal.Open(str(raster_path))
        assert restored_dataset is not None
        self.assertTrue(bool(restored_dataset.GetProjection()))
        restored_dataset = None

    def test_prepare_vsicurl_cog_can_be_uploaded_again(self) -> None:
        sandbox_group = self._create_sandbox_group()

        work_dir = self.create_temp_dir("-sandbox-raster")
        raster_path = work_dir / "source.tif"
        self._create_raster(raster_path, crs=self._epsg_3857())

        source_resource = self._upload_raster_resource(
            sandbox_group,
            raster_path,
            f"source-{uuid.uuid4().hex[:8]}",
            upload_as_cog=True,
        )
        remote_layer = self._vsicurl_layer(source_resource)
        self.assertEqual(remote_layer.crs().postgisSrid(), 3857)

        prepared = DownloadOnlyRasterUploadPreparer().prepare(remote_layer)
        self._register_prepared_cleanup(prepared)

        self.assertTrue(prepared.is_temporary)
        self.assertFalse(prepared.is_archive)
        self.assertEqual(prepared.upload_path.suffix, GEOTIFF_SUFFIX)

        prepared_layer = self._raster_layer(prepared.upload_path)
        self.assertEqual(prepared_layer.crs().postgisSrid(), 3857)

        dataset = gdal.Open(str(prepared.upload_path))
        assert dataset is not None
        self.assertTrue(bool(dataset.GetProjection()))
        dataset = None

        copied_resource = self._upload_raster_resource(
            sandbox_group,
            prepared.upload_path,
            f"copy-{uuid.uuid4().hex[:8]}",
            upload_as_cog=False,
        )
        self.assertEqual(copied_resource.common.cls, NGWRasterLayer.type_id)
