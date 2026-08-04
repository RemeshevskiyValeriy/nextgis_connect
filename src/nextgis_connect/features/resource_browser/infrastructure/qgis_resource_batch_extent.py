from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, auto
from typing import FrozenSet, List, Optional, Sequence, Set

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsMapLayer,
    QgsProject,
    QgsReferencedRectangle,
)
from qgis.gui import QgsMapCanvas

from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_extent import (
    QgisMapCanvasExtentApplicator,
)
from nextgis_connect.legacy.detached_editing.utils import is_ngw_container
from nextgis_connect.legacy.ngw.core import (
    NGWResource,
    NGWVectorLayer,
    NGWWebMap,
)
from nextgis_connect.legacy.ngw.core.ngw_resource import API_LAYER_EXTENT
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModel
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.extent_calculator import ExtentCalculator


class ResourceExtentKind(Enum):
    """Identify the exclusive source policy for a resource extent."""

    WEBMAP = auto()
    CACHED_VECTOR = auto()
    RESOURCE = auto()


@dataclass(frozen=True)
class ResourceExtentKey:
    """Identify one extent source within a configured connection."""

    connection_id: str
    resource_id: int


@dataclass(frozen=True)
class ResourceExtentSubject:
    """Describe one successfully imported resource for extent resolution."""

    key: ResourceExtentKey
    kind: ResourceExtentKind
    interfaces: FrozenSet[str] = frozenset()
    layer: Optional[QgsMapLayer] = None
    webmap_extent: Optional[QgsReferencedRectangle] = None


class ResourceExtentSubjectFactory:
    """Build neutral extent subjects from the legacy NGW resource model."""

    @staticmethod
    def from_layer(
        resource: NGWResource,
        layer: QgsMapLayer,
    ) -> ResourceExtentSubject:
        kind = ResourceExtentKind.RESOURCE
        if isinstance(resource, NGWVectorLayer) and is_ngw_container(layer):
            kind = ResourceExtentKind.CACHED_VECTOR

        return ResourceExtentSubject(
            key=ResourceExtentKey(
                resource.connection_id,
                resource.resource_id,
            ),
            kind=kind,
            interfaces=ResourceExtentSubjectFactory._interfaces(resource),
            layer=layer,
        )

    @staticmethod
    def from_webmap(webmap: NGWWebMap) -> ResourceExtentSubject:
        try:
            webmap_extent = webmap.extent
        except (TypeError, ValueError):
            logger.exception(
                f"Could not read Web map extent for resource "
                f"{webmap.resource_id}"
            )
            webmap_extent = None

        return ResourceExtentSubject(
            key=ResourceExtentKey(
                webmap.connection_id,
                webmap.resource_id,
            ),
            kind=ResourceExtentKind.WEBMAP,
            interfaces=ResourceExtentSubjectFactory._interfaces(webmap),
            webmap_extent=webmap_extent,
        )

    @staticmethod
    def _interfaces(resource: NGWResource) -> FrozenSet[str]:
        interfaces = getattr(resource.common, "interfaces", ())
        if not isinstance(interfaces, (list, tuple, set, frozenset)):
            return frozenset()

        return frozenset(
            interface for interface in interfaces if isinstance(interface, str)
        )


class BboxResourceExtentProvider(ABC):
    """Load the extent endpoint for a resource with IBboxLayer."""

    @abstractmethod
    def fetch(
        self,
        key: ResourceExtentKey,
    ) -> Optional[QgsReferencedRectangle]:
        """Return the resource extent in its referenced CRS."""


class LegacyBboxResourceExtentProvider(BboxResourceExtentProvider):
    """Fetch bbox through the connection owned by the legacy resource model."""

    def __init__(self, model: QNGWResourceTreeModel) -> None:
        self._model = model

    def fetch(
        self,
        key: ResourceExtentKey,
    ) -> Optional[QgsReferencedRectangle]:
        resource = self._model.resource(key.resource_id)
        if (
            resource is not None
            and resource.connection_id == key.connection_id
        ):
            response = resource.connection.get(
                API_LAYER_EXTENT(key.resource_id)
            )
        else:
            response = QgsNgwConnection(key.connection_id).get(
                API_LAYER_EXTENT(key.resource_id)
            )

        return ExtentCalculator.from_ngw_extent_dict(response)


class ResourceExtentStrategy(ABC):
    """Resolve one exclusive resource extent policy."""

    @abstractmethod
    def supports(self, subject: ResourceExtentSubject) -> bool:
        """Return whether this strategy owns the subject."""

    @abstractmethod
    def resolve(
        self,
        subject: ResourceExtentSubject,
    ) -> Optional[QgsReferencedRectangle]:
        """Resolve the subject extent without choosing a fallback policy."""


class WebMapExtentStrategy(ResourceExtentStrategy):
    """Use only the extent stored by a Web map resource."""

    def supports(self, subject: ResourceExtentSubject) -> bool:
        return subject.kind == ResourceExtentKind.WEBMAP

    def resolve(
        self,
        subject: ResourceExtentSubject,
    ) -> Optional[QgsReferencedRectangle]:
        return subject.webmap_extent


class CachedVectorExtentStrategy(ResourceExtentStrategy):
    """Use the local GeoPackage provider extent for cached vector layers."""

    def supports(self, subject: ResourceExtentSubject) -> bool:
        return subject.kind == ResourceExtentKind.CACHED_VECTOR

    def resolve(
        self,
        subject: ResourceExtentSubject,
    ) -> Optional[QgsReferencedRectangle]:
        if subject.layer is None:
            return None

        return ExtentCalculator.from_qgs_layer(subject.layer)


class BboxLayerExtentStrategy(ResourceExtentStrategy):
    """Use the NGW extent endpoint only for IBboxLayer resources."""

    INTERFACE = "IBboxLayer"

    def __init__(self, provider: BboxResourceExtentProvider) -> None:
        self._provider = provider

    def supports(self, subject: ResourceExtentSubject) -> bool:
        return self.INTERFACE in subject.interfaces

    def resolve(
        self,
        subject: ResourceExtentSubject,
    ) -> Optional[QgsReferencedRectangle]:
        return self._provider.fetch(subject.key)


class ResourceExtentResolver:
    """Select one extent strategy per resource and suppress duplicates."""

    def __init__(
        self,
        strategies: Sequence[ResourceExtentStrategy],
    ) -> None:
        self._strategies = tuple(strategies)

    def resolve(
        self,
        subjects: Sequence[ResourceExtentSubject],
    ) -> List[QgsReferencedRectangle]:
        extents: List[QgsReferencedRectangle] = []
        processed_keys: Set[ResourceExtentKey] = set()
        for subject in subjects:
            if subject.key in processed_keys:
                continue
            processed_keys.add(subject.key)

            strategy = next(
                (
                    candidate
                    for candidate in self._strategies
                    if candidate.supports(subject)
                ),
                None,
            )
            if strategy is None:
                continue

            try:
                extent = strategy.resolve(subject)
            except Exception:
                logger.exception(
                    f"Could not resolve extent for resource "
                    f"{subject.key.resource_id}"
                )
                continue

            if extent is not None:
                extents.append(extent)

        return extents


class QgisResourceBatchExtentCoordinator:
    """Collect, combine, and apply extents after a completed batch import."""

    def __init__(
        self,
        model: QNGWResourceTreeModel,
        canvas: Optional[QgsMapCanvas],
        project: Optional[QgsProject] = None,
        resolver: Optional[ResourceExtentResolver] = None,
        canvas_applicator: Optional[QgisMapCanvasExtentApplicator] = None,
    ) -> None:
        self._canvas = canvas
        self._project = project or QgsProject.instance()
        self._subjects: List[ResourceExtentSubject] = []
        self._resolver = resolver or ResourceExtentResolver(
            (
                WebMapExtentStrategy(),
                CachedVectorExtentStrategy(),
                BboxLayerExtentStrategy(
                    LegacyBboxResourceExtentProvider(model)
                ),
            )
        )
        self._canvas_applicator = (
            canvas_applicator or QgisMapCanvasExtentApplicator(canvas)
        )

    def add(self, subject: ResourceExtentSubject) -> None:
        """Register one successfully imported semantic resource."""
        self._subjects.append(subject)

    def apply(self) -> bool:
        """Combine all available extents and schedule one canvas update."""
        try:
            target_crs = self._target_crs()
            if target_crs is None:
                return False

            extent = ExtentCalculator.combine(
                self._resolver.resolve(self._subjects),
                target_crs,
            )
            if extent is None:
                return False

            return self._canvas_applicator.apply(extent)
        except Exception:
            logger.exception("Could not calculate imported resources extent")
            return False

    def clear(self) -> None:
        """Release references held for the completed import operation."""
        self._subjects.clear()

    def _target_crs(self) -> Optional[QgsCoordinateReferenceSystem]:
        if self._canvas is None:
            return None

        canvas_crs = self._canvas.mapSettings().destinationCrs()
        if canvas_crs.isValid():
            return canvas_crs

        project_crs = self._project.crs()
        if project_crs.isValid():
            return project_crs

        return None
