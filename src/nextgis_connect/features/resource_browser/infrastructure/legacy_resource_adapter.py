from typing import Optional, Union

from qgis.PyQt.QtCore import QModelIndex

from nextgis_connect.legacy.ngw.core import (
    NGWBaseMap,
    NGWOgcfService,
    NGWPostgisLayer,
    NGWQGISStyle,
    NGWRasterLayer,
    NGWResource,
    NGWTileset,
    NGWVectorLayer,
    NGWWebMap,
    NGWWfsLayer,
    NGWWfsService,
    NGWWmsConnection,
    NGWWmsLayer,
    NGWWmsService,
)
from nextgis_connect.legacy.ngw.core.ngw_tms_resources import (
    NGWTmsConnection,
    NGWTmsLayer,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem

TMS_LAYER_RESOURCE_TYPES = (
    NGWTmsLayer,
    NGWTmsConnection,
    NGWBaseMap,
    NGWTileset,
)
SERVICE_LAYER_RESOURCE_TYPES = (NGWPostgisLayer, NGWWmsLayer, NGWWfsLayer)
VECTOR_RESOURCE_TYPES = (NGWWfsLayer, NGWPostgisLayer)
RASTER_RESOURCE_TYPES = (
    NGWRasterLayer,
    *TMS_LAYER_RESOURCE_TYPES,
    NGWWmsLayer,
)
VECTOR_SERVICE_TYPES = (NGWWfsService, NGWOgcfService)
SERVICE_RESOURCE_TYPES = (*VECTOR_SERVICE_TYPES, NGWWmsService)
CONNECTION_RESOURCE_TYPES = (NGWWmsConnection,)


def resource_from_index(index: QModelIndex) -> Optional[NGWResource]:
    """Return the legacy resource stored by a model index."""
    resource = index.data(QNGWResourceItem.NGWResourceRole)
    return resource if isinstance(resource, NGWResource) else None


def is_style(
    resource: Union[Optional[NGWResource], QModelIndex],
) -> bool:
    if isinstance(resource, QModelIndex):
        resource = resource_from_index(resource)
    return isinstance(resource, NGWQGISStyle)


def is_layer(
    resource: Union[Optional[NGWResource], QModelIndex],
) -> bool:
    if isinstance(resource, QModelIndex):
        resource = resource_from_index(resource)
    return isinstance(
        resource,
        (NGWVectorLayer, *VECTOR_RESOURCE_TYPES, *RASTER_RESOURCE_TYPES),
    )


def is_webmap(
    resource: Union[Optional[NGWResource], QModelIndex],
) -> bool:
    if isinstance(resource, QModelIndex):
        resource = resource_from_index(resource)
    return isinstance(resource, NGWWebMap)


def is_service(
    resource: Union[Optional[NGWResource], QModelIndex],
) -> bool:
    if isinstance(resource, QModelIndex):
        resource = resource_from_index(resource)
    return isinstance(
        resource,
        (*VECTOR_SERVICE_TYPES, NGWWmsService, NGWWmsConnection),
    )
