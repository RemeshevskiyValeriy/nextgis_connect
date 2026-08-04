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

from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from qgis.PyQt.QtCore import QModelIndex

from nextgis_connect.legacy.ngw.core import (
    NGWGroupResource,
    NGWResource,
    NGWWebMap,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModel


@dataclass(frozen=True)
class ResourceSelectionResolution:
    """Store the effective selection after special resource resolution."""

    indices: Tuple[QModelIndex, ...]
    allow_demo_project_resolution: bool


class DemoProjectSelectionResolver:
    """Resolve every selected demo project to its first nested Web map."""

    def __init__(self, model: QNGWResourceTreeModel) -> None:
        self._model = model

    def resolve(
        self,
        indices: Sequence[QModelIndex],
        allow_resolution: bool,
    ) -> ResourceSelectionResolution:
        """Replace demo projects containing Web maps in the selection."""
        normalized_indices = tuple(indices)
        if not allow_resolution:
            return ResourceSelectionResolution(
                normalized_indices,
                False,
            )

        effective_indices = []
        has_demo_project = False
        for index in normalized_indices:
            resource = self._resource(index)
            if not self._is_demo_project(resource):
                effective_indices.append(index)
                continue

            has_demo_project = True
            webmap_index = self._find_webmap(index)
            effective_indices.append(
                webmap_index if webmap_index is not None else index
            )

        return ResourceSelectionResolution(
            tuple(effective_indices),
            not has_demo_project,
        )

    def _find_webmap(
        self,
        parent_index: QModelIndex,
    ) -> Optional[QModelIndex]:
        for row in range(self._model.rowCount(parent_index)):
            child_index = self._model.index(row, 0, parent_index)
            child_resource = self._resource(child_index)
            if isinstance(child_resource, NGWWebMap):
                return child_index
            if not isinstance(child_resource, NGWGroupResource):
                continue

            webmap_index = self._find_webmap(child_index)
            if webmap_index is not None:
                return webmap_index

        return None

    @staticmethod
    def _resource(index: QModelIndex) -> Optional[NGWResource]:
        return index.data(QNGWResourceItem.NGWResourceRole)

    @staticmethod
    def _is_demo_project(resource: Optional[NGWResource]) -> bool:
        return (
            isinstance(resource, NGWGroupResource)
            and getattr(resource.common, "cls", None) == "demo_project"
        )
