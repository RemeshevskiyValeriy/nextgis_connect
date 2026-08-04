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

from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_batch_import import (
    QgisResourceBatchImporter,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_extent import (
    QgisLayerSourceExtentApplicator,
    QgisMapCanvasExtentApplicator,
    QgisNetworkResourceExtentProvider,
    ResourceExtentProvider,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_import import (
    QgisLayerImportTarget,
    QgisResourceLayerImporter,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_style import (
    QgisResourceLayerStyleApplicator,
)
from nextgis_connect.features.resource_browser.infrastructure.resource_selection import (
    DemoProjectSelectionResolver,
)

__all__ = [
    "DemoProjectSelectionResolver",
    "QgisLayerImportTarget",
    "QgisLayerSourceExtentApplicator",
    "QgisMapCanvasExtentApplicator",
    "QgisNetworkResourceExtentProvider",
    "QgisResourceBatchImporter",
    "QgisResourceLayerImporter",
    "QgisResourceLayerStyleApplicator",
    "ResourceExtentProvider",
]
