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

from typing import List, Sequence, Tuple, Union

from qgis.PyQt.QtCore import QModelIndex

from nextgis_connect.features.resource_browser.infrastructure.legacy_resource_adapter import (
    SERVICE_LAYER_RESOURCE_TYPES,
    VECTOR_SERVICE_TYPES,
    is_layer,
    is_style,
    resource_from_index,
)
from nextgis_connect.legacy.ngw.core import (
    NGWGroupResource,
    NGWOgcfService,
    NGWQGISStyle,
    NGWResource,
    NGWWebMap,
    NGWWfsService,
)
from nextgis_connect.legacy.ngw.core.ngw_abstract_vector_resource import (
    NGWAbstractVectorResource,
)
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModel


class ResourceDependencyAnalyzer:
    """Discover resources and styles required by a batch import selection."""

    def __init__(self, model: QNGWResourceTreeModel) -> None:
        self._model = model

    def missing_resource_ids(
        self,
        indices: Sequence[QModelIndex],
    ) -> Tuple[int, ...]:
        resource_ids: List[int] = []
        for index in indices:
            effective_index = index.parent() if is_style(index) else index
            resource_ids.extend(self._missing_resources(effective_index))

        return tuple(dict.fromkeys(resource_ids))

    def missing_style_ids(
        self,
        indices: Sequence[QModelIndex],
    ) -> Tuple[int, ...]:
        style_ids: List[int] = []
        for index in indices:
            effective_index = index.parent() if is_style(index) else index
            style_ids.extend(self._missing_styles(effective_index))

        return tuple(dict.fromkeys(style_ids))

    def _missing_resources(self, index: QModelIndex) -> List[int]:
        resource = resource_from_index(index)
        if isinstance(resource, NGWGroupResource):
            return self._missing_resources_from_group(index, resource)
        if is_layer(resource):
            return self._missing_resources_from_layer(index)
        if isinstance(resource, NGWWebMap):
            return self._missing_resources_from_webmap(resource)
        if isinstance(resource, VECTOR_SERVICE_TYPES):
            return self._missing_resources_from_vector_service(resource)
        return []

    def _missing_resources_from_group(
        self,
        group_index: QModelIndex,
        group: NGWGroupResource,
    ) -> List[int]:
        if self._model.canFetchMore(group_index):
            return [group.resource_id]

        result: List[int] = []
        for row in range(self._model.rowCount(group_index)):
            child_index = self._model.index(row, 0, group_index)
            result.extend(self._missing_resources(child_index))
        return result

    def _missing_resources_from_webmap(
        self,
        webmap: NGWWebMap,
    ) -> List[int]:
        result: List[int] = []
        for resource_id in webmap.all_resources_id:
            if self._model.is_forbidden(resource_id):
                continue

            if not self._is_downloaded(resource_id):
                result.append(resource_id)
                continue

            resource = self._model.resource(resource_id)
            if not is_layer(resource):
                continue

            result.extend(self._missing_lookup_tables(resource))
            result.extend(self._missing_services(resource))
        return result

    def _missing_resources_from_vector_service(
        self,
        service: Union[NGWWfsService, NGWOgcfService],
    ) -> List[int]:
        result: List[int] = []
        for layer in service.layers:
            resource_id = layer.resource_id
            index = self._model.index_from_id(resource_id)
            resource = self._model.resource(resource_id)

            if self._model.is_forbidden(resource_id):
                continue
            if resource is None:
                result.append(resource_id)
            elif index is not None and index.isValid():
                result.extend(self._missing_resources_from_layer(index))
            else:
                styles = self._model.children_resources(resource_id)
                if resource.common.children and len(styles) == 0:
                    result.append(resource_id)
                result.extend(self._missing_lookup_tables(resource))
        return result

    def _missing_resources_from_layer(
        self,
        index: QModelIndex,
    ) -> List[int]:
        resource = resource_from_index(index)
        if resource is None:
            return []

        result: List[int] = []
        if self._model.canFetchMore(index):
            result.append(resource.resource_id)
        result.extend(self._missing_lookup_tables(resource))
        result.extend(self._missing_services(resource))
        return result

    def _missing_lookup_tables(
        self,
        resource: NGWResource,
    ) -> List[int]:
        if not isinstance(resource, NGWAbstractVectorResource):
            return []

        return [
            field.lookup_table
            for field in resource.fields
            if field.lookup_table is not None
            and not self._is_downloaded(field.lookup_table)
        ]

    def _missing_services(self, resource: NGWResource) -> List[int]:
        if not isinstance(resource, SERVICE_LAYER_RESOURCE_TYPES):
            return []
        if self._is_downloaded(resource.service_resource_id):
            return []
        return [resource.service_resource_id]

    def _is_downloaded(self, resource_id: int) -> bool:
        return self._model.resource(
            resource_id
        ) is not None or self._model.is_forbidden(resource_id)

    def _missing_styles(self, index: QModelIndex) -> List[int]:
        resource = resource_from_index(index)
        if isinstance(resource, NGWQGISStyle):
            return [] if resource.is_qml_populated else [resource.resource_id]

        if isinstance(resource, NGWWebMap):
            return [
                child.resource_id
                for resource_id in resource.all_resources_id
                for child in (self._model.resource(resource_id),)
                if isinstance(child, NGWQGISStyle)
                and not child.is_qml_populated
            ]

        if isinstance(resource, VECTOR_SERVICE_TYPES):
            return [
                child.resource_id
                for layer in resource.layers
                for child in self._model.children_resources(layer.resource_id)
                if isinstance(child, NGWQGISStyle)
                and not child.is_qml_populated
            ]

        result: List[int] = []
        for row in range(self._model.rowCount(index)):
            child_index = self._model.index(row, 0, index)
            result.extend(self._missing_styles(child_index))
        return result
