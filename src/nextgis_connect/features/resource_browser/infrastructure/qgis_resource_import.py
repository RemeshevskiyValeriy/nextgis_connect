from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Dict, Optional, Sequence

from qgis.core import (
    QgsLayerTreeGroup,
    QgsMapLayer,
    QgsProject,
    QgsProviderRegistry,
    QgsRasterLayer,
    QgsReferencedRectangle,
    QgsVectorLayer,
    QgsVectorTileLayer,
)
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, Qt, QThread, pyqtSignal, pyqtSlot

from nextgis_connect.features.resource_browser.domain.resource_import import (
    ResourceImportMode,
    ResourceImportRequest,
    ResourceImportSource,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_extent import (
    QgisLayerSourceExtentApplicator,
    QgisMapCanvasExtentApplicator,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_style import (
    QgisResourceLayerStyleApplicator,
)
from nextgis_connect.platform.logging import logger


class QgisLayerType(Enum):
    """Identify the QGIS layer class required by a provider definition."""

    VECTOR = auto()
    RASTER = auto()
    VECTOR_TILE = auto()


@dataclass(frozen=True)
class QgisLayerDefinition:
    """Store provider arguments needed to construct a QGIS layer."""

    uri: str
    name: str
    provider_key: str
    layer_type: QgisLayerType


@dataclass(frozen=True)
class QgisLayerImportTarget:
    """Describe a stable insertion point in the QGIS layer tree."""

    group: QgsLayerTreeGroup
    position: int

    def is_valid_for(self, project: QgsProject) -> bool:
        """Return whether the target group is alive in the project tree."""
        if sip.isdeleted(self.group):
            return False

        project_root = project.layerTreeRoot()
        current_group: Optional[QgsLayerTreeGroup] = self.group
        while current_group is not None:
            if current_group == project_root:
                return True

            parent = current_group.parent()
            current_group = (
                parent if isinstance(parent, QgsLayerTreeGroup) else None
            )

        return False

    def normalized_position(self) -> int:
        """Clamp the requested position to the current group boundaries."""
        return max(0, min(self.position, len(self.group.children())))


class ResourceLayerImportStrategy(ABC):
    """Build one provider-specific layer definition."""

    @property
    @abstractmethod
    def mode(self) -> ResourceImportMode:
        """Return the mode handled by this strategy."""

    @abstractmethod
    def create_definition(
        self,
        request: ResourceImportRequest,
    ) -> QgisLayerDefinition:
        """Create a QGIS provider definition for an import request."""

    def _authenticated_parameters(
        self,
        source: ResourceImportSource,
        url: str,
    ) -> Dict[str, Any]:
        parameters: Dict[str, Any] = {
            "type": "xyz",
            "url": url,
        }
        if source.auth_config_id is not None:
            parameters["authcfg"] = source.auth_config_id
        return parameters


class MvtResourceLayerImportStrategy(ResourceLayerImportStrategy):
    """Create an XYZ vector-tile definition for a feature layer."""

    @property
    def mode(self) -> ResourceImportMode:
        return ResourceImportMode.MVT

    def create_definition(
        self,
        request: ResourceImportRequest,
    ) -> QgisLayerDefinition:
        source = request.source
        url = (
            f"{source.connection_url.rstrip('/')}"
            "/api/component/feature_layer/mvt?"
            f"resource={source.resource_id}&z={{z}}&x={{x}}&y={{y}}"
        )
        provider_metadata = QgsProviderRegistry.instance().providerMetadata(
            "vectortile"
        )
        if provider_metadata is None:
            raise RuntimeError("QGIS vector tile provider is unavailable")

        uri = provider_metadata.encodeUri(
            self._authenticated_parameters(source, url)
        )
        return QgisLayerDefinition(
            uri=uri,
            name=source.display_name,
            provider_key="vectortile",
            layer_type=QgisLayerType.VECTOR_TILE,
        )


class TmsResourceLayerImportStrategy(ResourceLayerImportStrategy):
    """Create a rendered XYZ raster-tile definition."""

    @property
    def mode(self) -> ResourceImportMode:
        return ResourceImportMode.TMS

    def create_definition(
        self,
        request: ResourceImportRequest,
    ) -> QgisLayerDefinition:
        source = request.source
        resource_parameter = ",".join(
            str(resource_id) for resource_id in request.render_resource_ids
        )
        if resource_parameter == "":
            render_resource_id = request.render_resource_id
            if render_resource_id is None:
                render_resource_id = source.resource_id
            resource_parameter = str(render_resource_id)

        url = (
            f"{source.connection_url.rstrip('/')}"
            "/api/component/render/tile?"
            f"resource={resource_parameter}"
            f"&nd={request.no_data_response_code}"
            "&z={z}&x={x}&y={y}"
        )
        provider_metadata = QgsProviderRegistry.instance().providerMetadata(
            "wms"
        )
        if provider_metadata is None:
            raise RuntimeError("QGIS WMS provider is unavailable")

        uri = provider_metadata.encodeUri(
            self._authenticated_parameters(source, url)
        )
        return QgisLayerDefinition(
            uri=uri,
            name=source.display_name,
            provider_key="wms",
            layer_type=QgisLayerType.RASTER,
        )


class ExperimentalNgwResourceLayerImportStrategy(ResourceLayerImportStrategy):
    """Create a layer through GDAL's experimental NGW connection string."""

    @property
    def mode(self) -> ResourceImportMode:
        return ResourceImportMode.EXPERIMENTAL_NGW

    def create_definition(
        self,
        request: ResourceImportRequest,
    ) -> QgisLayerDefinition:
        source = request.source
        connection_url = (
            source.provider_connection_url or source.connection_url
        )
        resource_url = (
            f"{connection_url.rstrip('/')}/resource/{source.resource_id}"
        )
        return QgisLayerDefinition(
            uri=f"NGW:{resource_url}",
            name=source.display_name,
            provider_key="ogr",
            layer_type=QgisLayerType.VECTOR,
        )


class ResourceLayerImportStrategyFactory:
    """Resolve provider strategies by import mode."""

    def __init__(
        self,
        strategies: Optional[Sequence[ResourceLayerImportStrategy]] = None,
    ) -> None:
        configured_strategies = (
            tuple(strategies)
            if strategies is not None
            else (
                MvtResourceLayerImportStrategy(),
                TmsResourceLayerImportStrategy(),
                ExperimentalNgwResourceLayerImportStrategy(),
            )
        )
        self._strategies: Dict[
            ResourceImportMode, ResourceLayerImportStrategy
        ] = {}
        for strategy in configured_strategies:
            if strategy.mode in self._strategies:
                raise ValueError(
                    f"Duplicate resource import strategy: {strategy.mode}"
                )
            self._strategies[strategy.mode] = strategy

    def create_definition(
        self,
        request: ResourceImportRequest,
    ) -> QgisLayerDefinition:
        """Create a definition with the strategy matching the request."""
        try:
            strategy = self._strategies[request.mode]
        except KeyError as error:
            raise ValueError(
                f"Unsupported resource import mode: {request.mode}"
            ) from error

        return strategy.create_definition(request)


class QgisResourceLayerFactory:
    """Construct concrete QGIS layers from provider definitions."""

    def __init__(
        self,
        strategy_factory: Optional[ResourceLayerImportStrategyFactory] = None,
    ) -> None:
        self._strategy_factory = (
            strategy_factory or ResourceLayerImportStrategyFactory()
        )

    def create(self, request: ResourceImportRequest) -> QgsMapLayer:
        """Create a QGIS layer for a neutral resource import request."""
        definition = self._strategy_factory.create_definition(request)
        if definition.layer_type == QgisLayerType.VECTOR:
            return QgsVectorLayer(
                definition.uri,
                definition.name,
                definition.provider_key,
            )
        if definition.layer_type == QgisLayerType.RASTER:
            return QgsRasterLayer(
                definition.uri,
                definition.name,
                definition.provider_key,
            )
        if definition.layer_type == QgisLayerType.VECTOR_TILE:
            return QgsVectorTileLayer(
                definition.uri,
                definition.name,
            )

        raise ValueError(
            f"Unsupported QGIS layer type: {definition.layer_type}"
        )


class QgisResourceLayerImporter(QObject):
    """Insert directly represented Web GIS resources into a QGIS project."""

    layer_imported = pyqtSignal(str, name="layerImported")
    import_failed = pyqtSignal(str, name="importFailed")
    _import_requested = pyqtSignal(
        object,
        object,
        name="importRequested",
    )

    def __init__(
        self,
        parent: QObject,
        project: Optional[QgsProject] = None,
        layer_factory: Optional[QgisResourceLayerFactory] = None,
        extent_applicator: Optional[QgisLayerSourceExtentApplicator] = None,
        canvas_extent_applicator: Optional[
            QgisMapCanvasExtentApplicator
        ] = None,
        style_applicator: Optional[QgisResourceLayerStyleApplicator] = None,
    ) -> None:
        super().__init__(parent)
        self._project = project or QgsProject.instance()
        self._layer_factory = layer_factory or QgisResourceLayerFactory()
        self._extent_applicator = (
            extent_applicator or QgisLayerSourceExtentApplicator()
        )
        self._canvas_extent_applicator = canvas_extent_applicator
        self._style_applicator = (
            style_applicator or QgisResourceLayerStyleApplicator()
        )
        self._import_requested.connect(
            self._import_on_owner_thread,
            type=Qt.ConnectionType.QueuedConnection,
        )

    def import_resource(
        self,
        request: ResourceImportRequest,
        target: QgisLayerImportTarget,
    ) -> None:
        """Schedule layer creation in the importer's affinity thread."""
        if QThread.currentThread() != self.thread():
            self._import_requested.emit(request, target)
            return

        self._import_on_owner_thread(request, target)

    @pyqtSlot(object, object)
    def _import_on_owner_thread(
        self,
        request: ResourceImportRequest,
        target: QgisLayerImportTarget,
    ) -> None:
        """Create, register, and insert a layer in the QGIS GUI thread."""
        try:
            self._validate_target(target)
            layer = self._layer_factory.create(request)
            if not layer.isValid():
                error_summary = layer.error().summary()
                raise RuntimeError(
                    error_summary or "QGIS could not create the layer"
                )

            source = request.source
            layer.setCustomProperty("ngw_connection_id", source.connection_id)
            layer.setCustomProperty(
                "ngw_instance_id",
                source.connection_instance_id,
            )
            layer.setCustomProperty("ngw_resource_id", source.resource_id)

            source_extent = self._resolve_source_extent(request)
            if source_extent is not None:
                self._extent_applicator.apply_referenced_extent(
                    source_extent,
                    layer,
                )

            self._style_applicator.apply(
                request.styles,
                layer,
                request.default_style_name,
            )

            self._validate_target(target)
            registered_layer = self._insert_layer(layer, target)
            if (
                source_extent is not None
                and self._canvas_extent_applicator is not None
            ):
                self._canvas_extent_applicator.apply(source_extent)
            self.layer_imported.emit(registered_layer.id())
        except Exception as error:
            error_message = self._safe_error_message(error, request.source)
            if request.source.provider_connection_url is None:
                logger.exception("Could not import a Web GIS resource layer")
            else:
                logger.error(
                    "Could not import a Web GIS resource layer: "
                    f"{error_message}"
                )
            self.import_failed.emit(
                self._resource_error_message(error_message, request.source)
            )

    @staticmethod
    def _safe_error_message(
        error: Exception,
        source: ResourceImportSource,
    ) -> str:
        error_message = str(error)
        if source.provider_connection_url is None:
            return error_message

        return error_message.replace(
            source.provider_connection_url,
            source.connection_url,
        )

    @staticmethod
    def _resource_error_message(
        error_message: str,
        source: ResourceImportSource,
    ) -> str:
        resource_message = (
            f'Resource "{source.display_name}" (id={source.resource_id})'
        )
        if len(error_message) == 0:
            return resource_message

        return f"{resource_message}: {error_message}"

    def _insert_layer(
        self,
        layer: QgsMapLayer,
        target: QgisLayerImportTarget,
    ) -> QgsMapLayer:
        layer_id = layer.id()
        registered_layer = self._project.addMapLayer(
            layer,
            addToLegend=False,
        )
        if (
            registered_layer is None
            or sip.isdeleted(registered_layer)
            or self._project.mapLayer(layer_id) is None
        ):
            raise RuntimeError("QGIS could not take ownership of the layer")

        try:
            self._validate_target(target)
            layer_node = target.group.insertLayer(
                target.normalized_position(),
                registered_layer,
            )
            if layer_node is None:
                raise RuntimeError("QGIS could not insert the layer")

            layer_node.setExpanded(True)
            return registered_layer
        except Exception:
            if self._project.mapLayer(layer_id) is not None:
                self._project.removeMapLayer(layer_id)
            raise

    def _validate_target(self, target: QgisLayerImportTarget) -> None:
        if not target.is_valid_for(self._project):
            raise RuntimeError("The target layer tree group no longer exists")

    def _resolve_source_extent(
        self,
        request: ResourceImportRequest,
    ) -> Optional[QgsReferencedRectangle]:
        if not self._should_apply_source_extent(request):
            return None

        if request.source_extent is not None:
            return self._extent_applicator.create_import_extent(
                request.source_extent
            )

        return self._extent_applicator.fetch_source_extent(request.source)

    @staticmethod
    def _should_apply_source_extent(
        request: ResourceImportRequest,
    ) -> bool:
        return request.mode in (
            ResourceImportMode.MVT,
            ResourceImportMode.TMS,
        )
