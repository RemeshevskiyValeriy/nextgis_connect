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

from typing import Optional

from qgis.core import QgsMapLayer
from qgis.gui import QgsAbstractMapToolHandler, QgsMapTool
from qgis.PyQt.QtWidgets import QAction
from qgis.utils import iface

from nextgis_connect.legacy.detached_editing.utils import is_ngw_container


class IdentificationToolHandler(QgsAbstractMapToolHandler):
    """Restrict the identification tool to supported layers.

    Delegate base map-tool handler behavior to QGIS and only expose the
    identification action for layers that represent NGW containers in the
    detached editing workflow.

    :ivar map_tool: Map tool instance managed by the handler.
    :ivar action: QAction associated with the map tool.
    """

    def __init__(self, map_tool: QgsMapTool, action: QAction) -> None:  # pyright: ignore[reportInvalidTypeForm]
        """Initialize the handler.

        :param map_tool: Map tool used for identification.
        :param action: Associated QAction.
        """
        super().__init__(map_tool, action)

    def isCompatibleWithLayer(
        self,
        layer: Optional[QgsMapLayer],
        context: QgsAbstractMapToolHandler.Context,
    ) -> bool:
        """Return whether the handler supports the provided layer.

        Treat a layer as compatible when it is not ``None`` and represents
        an NGW container according to
        ``nextgis_connect.legacy.detached_editing.utils.is_ngw_container``.

        :param layer: Layer to check compatibility for, may be ``None``.
        :param context: Context of the map tool handler.
        :return: Return True when the layer is an NGW container.
        """
        if layer is not None and is_ngw_container(layer):
            return True

        layer_tree_view = iface.layerTreeView()
        if layer_tree_view is None:
            return False

        return any(
            is_ngw_container(selected_layer)
            for selected_layer in layer_tree_view.selectedLayersRecursive()
        )
