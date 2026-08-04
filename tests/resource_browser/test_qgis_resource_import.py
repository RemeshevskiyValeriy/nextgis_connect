import json
import threading
from unittest import mock

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsMapLayer,
    QgsMapLayerStyle,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsVectorLayer,
    QgsVectorTileLayer,
)
from qgis.PyQt.QtCore import QByteArray, QObject, QThread
from qgis.PyQt.QtNetwork import QNetworkReply
from qgis.PyQt.QtTest import QSignalSpy

from nextgis_connect.features.resource_browser.domain import (
    ResourceImportExtent,
    ResourceImportMode,
    ResourceImportRequest,
    ResourceImportSource,
    ResourceImportStyle,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_extent import (
    QgisLayerSourceExtentApplicator,
    QgisMapCanvasExtentApplicator,
    QgisNetworkResourceExtentProvider,
    ResourceExtentProvider,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_import import (
    MvtResourceLayerImportStrategy,
    QgisLayerImportTarget,
    QgisLayerType,
    QgisResourceLayerFactory,
    QgisResourceLayerImporter,
    ResourceLayerImportStrategyFactory,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_style import (
    QgisResourceLayerStyleApplicator,
)
from nextgis_connect.platform.qgis.extent_calculator import ExtentCalculator


class _MemoryLayerFactory(QgisResourceLayerFactory):
    def __init__(self) -> None:
        super().__init__()
        self.creation_thread = None

    def create(self, request: ResourceImportRequest) -> QgsVectorLayer:
        self.creation_thread = QThread.currentThread()
        return QgsVectorLayer(
            "Point?crs=EPSG:3857", request.source.display_name, "memory"
        )


class _RecordingExtentProvider(ResourceExtentProvider):
    def __init__(self, extent: QgsReferencedRectangle) -> None:
        self.extent = extent
        self.sources = []

    def fetch(
        self,
        source: ResourceImportSource,
    ) -> QgsReferencedRectangle:
        self.sources.append(source)
        return self.extent


class _TargetGroupRemovingObserver(QObject):
    def __init__(self, project_root, target_group) -> None:
        super().__init__()
        self._project_root = project_root
        self._target_group = target_group

    def remove_target_group(self, added_layers) -> None:
        del added_layers
        self._project_root.removeChildNode(self._target_group)


class TestResourceLayerImportStrategyFactory:
    def test_constructs_concrete_qgis_tile_layers(self, qgis_app) -> None:
        del qgis_app
        source = self._source()
        factory = QgisResourceLayerFactory()

        mvt_layer = factory.create(
            ResourceImportRequest(ResourceImportMode.MVT, source)
        )
        tms_layer = factory.create(
            ResourceImportRequest(ResourceImportMode.TMS, source)
        )

        assert isinstance(mvt_layer, QgsVectorTileLayer)
        assert mvt_layer.isValid()
        assert isinstance(tms_layer, QgsRasterLayer)
        assert tms_layer.isValid()

    def test_constructs_experimental_ngw_vector_layer(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        source = self._source()

        layer = QgisResourceLayerFactory().create(
            ResourceImportRequest(ResourceImportMode.EXPERIMENTAL_NGW, source)
        )

        assert isinstance(layer, QgsVectorLayer)
        assert layer.name() == source.display_name
        assert layer.providerType() == "ogr"
        assert layer.source() == (
            "NGW:https://user:password@example.nextgis.com/resource/7155"
        )

    def test_respects_explicit_empty_strategy_collection(self) -> None:
        factory = ResourceLayerImportStrategyFactory(())
        request = ResourceImportRequest(
            mode=ResourceImportMode.MVT,
            source=self._source(),
        )

        with pytest.raises(ValueError, match="Unsupported resource import"):
            factory.create_definition(request)

    def test_rejects_duplicate_strategy_modes(self) -> None:
        with pytest.raises(ValueError, match="Duplicate resource import"):
            ResourceLayerImportStrategyFactory(
                (
                    MvtResourceLayerImportStrategy(),
                    MvtResourceLayerImportStrategy(),
                )
            )

    def test_creates_mvt_provider_definition(self, qgis_app) -> None:
        del qgis_app
        request = ResourceImportRequest(
            mode=ResourceImportMode.MVT,
            source=self._source(),
        )

        definition = ResourceLayerImportStrategyFactory().create_definition(
            request
        )
        parameters = (
            QgsProviderRegistry.instance()
            .providerMetadata("vectortile")
            .decodeUri(definition.uri)
        )

        assert definition.layer_type == QgisLayerType.VECTOR_TILE
        assert parameters["url"] == (
            "https://example.nextgis.com/api/component/feature_layer/mvt?"
            "resource=7155&z={z}&x={x}&y={y}"
        )
        assert parameters["authcfg"] == "auth-id"

    def test_creates_tms_provider_definition_for_selected_style(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        request = ResourceImportRequest(
            mode=ResourceImportMode.TMS,
            source=self._source(),
            render_resource_id=6160,
        )

        definition = ResourceLayerImportStrategyFactory().create_definition(
            request
        )
        parameters = (
            QgsProviderRegistry.instance()
            .providerMetadata("wms")
            .decodeUri(definition.uri)
        )

        assert definition.layer_type == QgisLayerType.RASTER
        assert parameters["url"] == (
            "https://example.nextgis.com/api/component/render/tile?"
            "resource=6160&nd=204&z={z}&x={x}&y={y}"
        )
        assert parameters["authcfg"] == "auth-id"

    def test_creates_tms_provider_definition_for_webmap_layers(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        request = ResourceImportRequest(
            mode=ResourceImportMode.TMS,
            source=self._source(),
            render_resource_ids=(
                264,
                263,
                262,
                261,
                260,
                259,
                258,
                257,
                256,
                255,
                254,
                266,
            ),
        )

        definition = ResourceLayerImportStrategyFactory().create_definition(
            request
        )
        parameters = (
            QgsProviderRegistry.instance()
            .providerMetadata("wms")
            .decodeUri(definition.uri)
        )

        assert parameters["url"] == (
            "https://example.nextgis.com/api/component/render/tile?"
            "resource=264,263,262,261,260,259,258,257,256,255,254,266"
            "&nd=204&z={z}&x={x}&y={y}"
        )

    def test_creates_tms_provider_definition_for_multiple_webmap_layers(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        request = ResourceImportRequest(
            mode=ResourceImportMode.TMS,
            source=self._source(),
            render_resource_ids=(
                22,
                21,
                19,
                20,
            ),
        )

        definition = ResourceLayerImportStrategyFactory().create_definition(
            request
        )
        parameters = (
            QgsProviderRegistry.instance()
            .providerMetadata("wms")
            .decodeUri(definition.uri)
        )

        assert parameters["url"] == (
            "https://example.nextgis.com/api/component/render/tile?"
            "resource=22,21,19,20&nd=204&z={z}&x={x}&y={y}"
        )

    def test_creates_experimental_ngw_definition(self, qgis_app) -> None:
        del qgis_app
        request = ResourceImportRequest(
            mode=ResourceImportMode.EXPERIMENTAL_NGW,
            source=self._source(),
        )

        definition = ResourceLayerImportStrategyFactory().create_definition(
            request
        )

        assert definition.layer_type == QgisLayerType.VECTOR
        assert definition.provider_key == "ogr"
        assert definition.uri == (
            "NGW:https://user:password@example.nextgis.com/resource/7155"
        )

    def _source(self) -> ResourceImportSource:
        return ResourceImportSource(
            connection_url="https://example.nextgis.com/",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
            auth_config_id="auth-id",
            provider_connection_url=(
                "https://user:password@example.nextgis.com/"
            ),
        )


class TestQgisResourceLayerImporter:
    def test_inserts_layer_and_preserves_resource_link(self, qgis_app) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
        )
        imported_spy = QSignalSpy(importer.layer_imported)
        failed_spy = QSignalSpy(importer.import_failed)
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )

        importer.import_resource(
            ResourceImportRequest(ResourceImportMode.MVT, source),
            QgisLayerImportTarget(project.layerTreeRoot(), 0),
        )

        assert len(failed_spy) == 0
        assert len(imported_spy) == 1
        layer = project.mapLayer(imported_spy[0][0])
        assert layer is not None
        assert layer.customProperty("ngw_connection_id") == "connection-id"
        assert layer.customProperty("ngw_instance_id") == "instance-id"
        assert layer.customProperty("ngw_resource_id") == 7155
        assert project.layerTreeRoot().findLayer(layer.id()) is not None

        project.clear()
        parent.deleteLater()

    def test_rejects_target_outside_project_tree(self, qgis_app) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        foreign_project = QgsProject()
        parent = QObject()
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
        )
        failed_spy = QSignalSpy(importer.import_failed)
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )

        importer.import_resource(
            ResourceImportRequest(ResourceImportMode.MVT, source),
            QgisLayerImportTarget(foreign_project.layerTreeRoot(), 0),
        )

        assert len(failed_spy) == 1
        assert "no longer exists" in failed_spy[0][0]
        assert project.count() == 0

        parent.deleteLater()

    def test_rolls_back_layer_if_target_is_deleted_during_registration(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        target_group = project.layerTreeRoot().addGroup("Temporary")
        observer = _TargetGroupRemovingObserver(
            project.layerTreeRoot(),
            target_group,
        )
        project.layersAdded.connect(observer.remove_target_group)
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
        )
        failed_spy = QSignalSpy(importer.import_failed)
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )

        importer.import_resource(
            ResourceImportRequest(ResourceImportMode.MVT, source),
            QgisLayerImportTarget(target_group, 0),
        )

        assert len(failed_spy) == 1
        assert "no longer exists" in failed_spy[0][0]
        assert project.count() == 0

        project.layersAdded.disconnect(observer.remove_target_group)
        observer.deleteLater()
        parent.deleteLater()

    def test_queues_qgis_layer_creation_to_owner_thread(
        self,
        qgis_app,
    ) -> None:
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        layer_factory = _MemoryLayerFactory()
        importer = QgisResourceLayerImporter(
            parent,
            project,
            layer_factory,
        )
        imported_spy = QSignalSpy(importer.layer_imported)
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        request = ResourceImportRequest(ResourceImportMode.MVT, source)
        target = QgisLayerImportTarget(project.layerTreeRoot(), 0)

        worker = threading.Thread(
            target=importer.import_resource,
            args=(request, target),
        )
        worker.start()
        worker.join()
        qgis_app.processEvents()

        assert len(imported_spy) == 1
        assert layer_factory.creation_thread == importer.thread()
        assert project.count() == 1

        project.clear()
        parent.deleteLater()

    def test_applies_original_resource_extent_to_alternative_tms(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        source_extent = QgsReferencedRectangle(
            QgsRectangle(10.0, 20.0, 30.0, 40.0),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        extent_provider = _RecordingExtentProvider(source_extent)
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
            QgisLayerSourceExtentApplicator(extent_provider),
        )

        importer.import_resource(
            ResourceImportRequest(
                ResourceImportMode.TMS,
                source,
                render_resource_id=6160,
            ),
            QgisLayerImportTarget(project.layerTreeRoot(), 0),
        )

        imported_layer = next(iter(project.mapLayers().values()))
        assert imported_layer.isValid()
        assert extent_provider.sources == [source]

        project.clear()
        parent.deleteLater()

    def test_applies_original_resource_extent_to_mvt(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        source_extent = QgsReferencedRectangle(
            QgsRectangle(10.0, 20.0, 30.0, 40.0),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        extent_provider = _RecordingExtentProvider(source_extent)
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
            QgisLayerSourceExtentApplicator(extent_provider),
        )

        importer.import_resource(
            ResourceImportRequest(
                ResourceImportMode.MVT,
                source,
            ),
            QgisLayerImportTarget(project.layerTreeRoot(), 0),
        )

        imported_layer = next(iter(project.mapLayers().values()))
        assert imported_layer.isValid()
        assert extent_provider.sources == [source]

        project.clear()
        parent.deleteLater()

    def test_applies_request_extent_to_tms_without_network_extent_fetch(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        extent_applicator = mock.Mock(spec=QgisLayerSourceExtentApplicator)
        referenced_extent = QgsReferencedRectangle(
            QgsRectangle(10.0, 20.0, 30.0, 40.0),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        extent_applicator.create_import_extent.return_value = referenced_extent
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
            extent_applicator,
        )
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        source_extent = ResourceImportExtent(
            x_min=10.0,
            y_min=20.0,
            x_max=30.0,
            y_max=40.0,
        )

        importer.import_resource(
            ResourceImportRequest(
                ResourceImportMode.TMS,
                source,
                source_extent=source_extent,
            ),
            QgisLayerImportTarget(project.layerTreeRoot(), 0),
        )

        imported_layer = next(iter(project.mapLayers().values()))
        extent_applicator.create_import_extent.assert_called_once_with(
            source_extent,
        )
        extent_applicator.fetch_source_extent.assert_not_called()
        extent_applicator.apply_referenced_extent.assert_called_once_with(
            referenced_extent,
            imported_layer,
        )

        project.clear()
        parent.deleteLater()

    def test_applies_mvt_source_extent_to_canvas_after_layer_insert(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        existing_layer = QgsVectorLayer(
            "Point?crs=EPSG:3857",
            "Existing layer",
            "memory",
        )
        project.addMapLayer(existing_layer)
        parent = QObject()
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        source_extent = QgsReferencedRectangle(
            QgsRectangle(10.0, 20.0, 30.0, 40.0),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        canvas_extent_applicator = mock.Mock(
            spec=QgisMapCanvasExtentApplicator
        )
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
            QgisLayerSourceExtentApplicator(
                _RecordingExtentProvider(source_extent)
            ),
            canvas_extent_applicator,
        )

        importer.import_resource(
            ResourceImportRequest(ResourceImportMode.MVT, source),
            QgisLayerImportTarget(project.layerTreeRoot(), 0),
        )

        assert project.count() == 2
        canvas_extent_applicator.apply.assert_called_once_with(source_extent)

        project.clear()
        parent.deleteLater()

    def test_applies_requested_styles_before_project_registration(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        project = QgsProject.instance()
        project.clear()
        parent = QObject()
        style_applicator = mock.Mock(spec=QgisResourceLayerStyleApplicator)
        importer = QgisResourceLayerImporter(
            parent,
            project,
            _MemoryLayerFactory(),
            style_applicator=style_applicator,
        )
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        styles = (ResourceImportStyle(name="Style", qml="QML"),)

        importer.import_resource(
            ResourceImportRequest(
                ResourceImportMode.EXPERIMENTAL_NGW,
                source,
                styles=styles,
            ),
            QgisLayerImportTarget(project.layerTreeRoot(), 0),
        )

        style_applicator.apply.assert_called_once()
        applied_styles, applied_layer, default_style_name = (
            style_applicator.apply.call_args.args
        )
        assert applied_styles == styles
        assert default_style_name is None
        assert project.mapLayer(applied_layer.id()) is applied_layer

        project.clear()
        parent.deleteLater()

    def test_redacts_provider_credentials_from_import_error(
        self,
    ) -> None:
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
            provider_connection_url=(
                "https://username:password@example.nextgis.com"
            ),
        )
        error = RuntimeError(
            "Failed to open "
            "https://username:password@example.nextgis.com/resource/7155"
        )

        error_message = QgisResourceLayerImporter._safe_error_message(
            error,
            source,
        )

        assert error_message == (
            "Failed to open https://example.nextgis.com/resource/7155"
        )


class TestQgisLayerSourceExtentApplicator:
    def test_transforms_and_applies_source_extent(self, qgis_app) -> None:
        del qgis_app
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Test layer",
        )
        source_extent = QgsReferencedRectangle(
            QgsRectangle(10.0, 20.0, 30.0, 40.0),
            QgsCoordinateReferenceSystem.fromEpsgId(4326),
        )
        target_crs = QgsCoordinateReferenceSystem.fromEpsgId(3857)
        extent_provider = _RecordingExtentProvider(source_extent)
        layer = mock.Mock(spec=QgsMapLayer)
        layer.crs.return_value = target_crs

        is_applied = QgisLayerSourceExtentApplicator(extent_provider).apply(
            source, layer
        )

        expected_extent = ExtentCalculator.transform(
            source_extent,
            target_crs,
        )
        assert expected_extent is not None
        assert is_applied is True
        assert extent_provider.sources == [source]
        applied_extent = layer.setExtent.call_args.args[0]
        assert applied_extent.xMinimum() == pytest.approx(
            expected_extent.xMinimum()
        )
        assert applied_extent.yMinimum() == pytest.approx(
            expected_extent.yMinimum()
        )
        assert applied_extent.xMaximum() == pytest.approx(
            expected_extent.xMaximum()
        )
        assert applied_extent.yMaximum() == pytest.approx(
            expected_extent.yMaximum()
        )

    def test_transforms_and_applies_request_extent(self, qgis_app) -> None:
        del qgis_app
        source_extent = ResourceImportExtent(
            x_min=10.0,
            y_min=20.0,
            x_max=30.0,
            y_max=40.0,
        )
        target_crs = QgsCoordinateReferenceSystem.fromEpsgId(3857)
        layer = mock.Mock(spec=QgsMapLayer)
        layer.crs.return_value = target_crs

        is_applied = QgisLayerSourceExtentApplicator().apply_import_extent(
            source_extent,
            layer,
        )

        expected_extent = ExtentCalculator.transform(
            QgsReferencedRectangle(
                QgsRectangle(10.0, 20.0, 30.0, 40.0),
                QgsCoordinateReferenceSystem.fromEpsgId(4326),
            ),
            target_crs,
        )
        assert expected_extent is not None
        assert is_applied is True
        applied_extent = layer.setExtent.call_args.args[0]
        assert applied_extent.xMinimum() == pytest.approx(
            expected_extent.xMinimum()
        )
        assert applied_extent.yMinimum() == pytest.approx(
            expected_extent.yMinimum()
        )
        assert applied_extent.xMaximum() == pytest.approx(
            expected_extent.xMaximum()
        )
        assert applied_extent.yMaximum() == pytest.approx(
            expected_extent.yMaximum()
        )


class TestQgisResourceLayerStyleApplicator:
    def test_adds_styles_and_selects_layer_name(self, qgis_app) -> None:
        del qgis_app
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3857",
            "Layer style",
            "memory",
        )
        qml = self._layer_qml(layer)
        styles = (
            ResourceImportStyle(name="Other style", qml=qml),
            ResourceImportStyle(name="Layer style", qml=qml),
        )

        is_applied = QgisResourceLayerStyleApplicator().apply(styles, layer)

        style_manager = layer.styleManager()
        assert is_applied is True
        assert style_manager.styles() == ["Layer style", "Other style"]
        assert style_manager.currentStyle() == "Layer style"

    def test_selects_first_sorted_style_without_name_match(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3857",
            "Source layer",
            "memory",
        )
        qml = self._layer_qml(layer)
        styles = (
            ResourceImportStyle(name="Zulu", qml=qml),
            ResourceImportStyle(name="Alpha", qml=qml),
        )

        QgisResourceLayerStyleApplicator().apply(styles, layer)

        assert layer.styleManager().currentStyle() == "Alpha"

    def test_selects_explicit_default_style(self, qgis_app) -> None:
        del qgis_app
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3857",
            "Source layer",
            "memory",
        )
        qml = self._layer_qml(layer)
        styles = (
            ResourceImportStyle(name="First", qml=qml),
            ResourceImportStyle(name="Selected", qml=qml),
        )

        QgisResourceLayerStyleApplicator().apply(
            styles,
            layer,
            "Selected",
        )

        assert layer.styleManager().currentStyle() == "Selected"

    def test_rejects_invalid_style_without_modifying_layer(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3857",
            "Source layer",
            "memory",
        )
        style_manager = layer.styleManager()
        original_styles = style_manager.styles()
        original_current_style = style_manager.currentStyle()

        with pytest.raises(RuntimeError, match="is not valid"):
            QgisResourceLayerStyleApplicator().apply(
                (ResourceImportStyle(name="Broken", qml="not qml"),),
                layer,
            )

        assert style_manager.styles() == original_styles
        assert style_manager.currentStyle() == original_current_style

    def test_rolls_back_when_default_style_is_unavailable(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        layer = QgsVectorLayer(
            "Point?crs=EPSG:3857",
            "Source layer",
            "memory",
        )
        style_manager = layer.styleManager()
        original_styles = style_manager.styles()
        original_current_style = style_manager.currentStyle()
        qml = self._layer_qml(layer)

        with pytest.raises(RuntimeError, match="is unavailable"):
            QgisResourceLayerStyleApplicator().apply(
                (ResourceImportStyle(name="Available", qml=qml),),
                layer,
                "Missing",
            )

        assert style_manager.styles() == original_styles
        assert style_manager.currentStyle() == original_current_style

    @staticmethod
    def _layer_qml(layer: QgsMapLayer) -> str:
        style = QgsMapLayerStyle()
        style.readFromLayer(layer)
        assert style.isValid()
        return style.xmlData()


class TestQgisNetworkResourceExtentProvider:
    def test_requests_extent_for_original_source_resource(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        source = ResourceImportSource(
            connection_url="https://example.nextgis.com/",
            connection_id="connection-id",
            connection_instance_id="instance-id",
            resource_id=7155,
            display_name="Source layer",
            auth_config_id="auth-id",
        )
        response = mock.Mock()
        response.error.return_value = QNetworkReply.NetworkError.NoError
        response.content.return_value = QByteArray(
            json.dumps(
                {
                    "extent": {
                        "minLon": 10.0,
                        "minLat": 20.0,
                        "maxLon": 30.0,
                        "maxLat": 40.0,
                    }
                }
            ).encode("utf-8")
        )

        with mock.patch(
            "nextgis_connect.features.resource_browser.infrastructure."
            "qgis_resource_extent.QgsNetworkAccessManager.blockingGet",
            return_value=response,
        ) as blocking_get:
            extent = QgisNetworkResourceExtentProvider().fetch(source)

        request = blocking_get.call_args.args[0]
        assert request.url().toString() == (
            "https://example.nextgis.com/api/resource/7155/extent"
        )
        assert blocking_get.call_args.args[1:] == ("auth-id", False)
        assert extent is not None
        assert extent.crs().authid() == "EPSG:4326"
        assert extent.xMinimum() == pytest.approx(10.0)
        assert extent.yMinimum() == pytest.approx(20.0)
        assert extent.xMaximum() == pytest.approx(30.0)
        assert extent.yMaximum() == pytest.approx(40.0)
