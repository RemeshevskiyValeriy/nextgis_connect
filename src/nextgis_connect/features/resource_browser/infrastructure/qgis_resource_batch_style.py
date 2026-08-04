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

from typing import List, Optional, Sequence, Union

from qgis.core import QgsMapLayer
from qgis.PyQt.QtCore import QModelIndex

from nextgis_connect.features.resource_browser.domain import (
    ResourceImportStyle,
)
from nextgis_connect.features.resource_browser.infrastructure.legacy_resource_adapter import (
    is_style,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_style import (
    QgisResourceLayerStyleApplicator,
)
from nextgis_connect.legacy.ngw.core import (
    NGWQGISStyle,
    NGWResource,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModel
from nextgis_connect.platform.qgis.errors import ErrorCode, NgConnectError


class QgisResourceBatchStyleApplicator:
    """Adapt legacy NGW styles to the shared QGIS style applicator."""

    def __init__(
        self,
        resource_model: QNGWResourceTreeModel,
        style_applicator: Optional[QgisResourceLayerStyleApplicator] = None,
    ) -> None:
        self._resource_model = resource_model
        self._style_applicator = (
            style_applicator or QgisResourceLayerStyleApplicator()
        )

    def style_resources(
        self,
        layer: Union[QModelIndex, NGWResource],
    ) -> List[NGWQGISStyle]:
        """Return all populated or pending style resources for a layer."""
        if isinstance(layer, QModelIndex):
            layer_index = layer.parent() if is_style(layer) else layer
            styles = []
            for row in range(self._resource_model.rowCount(layer_index)):
                style_index = self._resource_model.index(
                    row,
                    0,
                    layer_index,
                )
                style = style_index.data(QNGWResourceItem.NGWResourceRole)
                if isinstance(style, NGWQGISStyle):
                    styles.append(style)
            return styles

        return [
            style
            for style in self._resource_model.children_resources(
                layer.resource_id
            )
            if isinstance(style, NGWQGISStyle)
        ]

    def apply_all(
        self,
        source: Union[QModelIndex, NGWResource],
        layer: QgsMapLayer,
        default_style_id: Optional[int] = None,
    ) -> None:
        """Register all source styles and select the requested default."""
        styles = sorted(
            self.style_resources(source),
            key=lambda resource: resource.display_name,
        )
        if len(styles) == 0:
            return

        default_style_name = next(
            (
                style.display_name
                for style in styles
                if style.resource_id == default_style_id
            ),
            None,
        )
        self._apply(styles, layer, default_style_name)

    def replace_default(
        self,
        style_resource: NGWQGISStyle,
        layer: QgsMapLayer,
    ) -> None:
        """Replace the provider-created default with one explicit style."""
        self._apply(
            (style_resource,),
            layer,
            style_resource.display_name,
        )

    def _apply(
        self,
        style_resources: Sequence[NGWQGISStyle],
        layer: QgsMapLayer,
        default_style_name: Optional[str],
    ) -> None:
        styles = []
        for style_resource in style_resources:
            if not style_resource.is_qml_populated:
                raise NgConnectError(
                    code=ErrorCode.AddingError,
                    log_message=(
                        f'QML for style "{style_resource.display_name}"'
                        " is not downloaded"
                    ),
                )
            styles.append(
                ResourceImportStyle(
                    style_resource.display_name,
                    style_resource.qml,
                )
            )

        try:
            self._style_applicator.apply(
                tuple(styles),
                layer,
                default_style_name,
            )
        except RuntimeError as error:
            raise NgConnectError(
                code=ErrorCode.AddingError,
                log_message=str(error),
            ) from error
