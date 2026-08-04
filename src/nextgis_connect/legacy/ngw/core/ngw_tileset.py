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

from typing import Tuple

from qgis.core import QgsProviderRegistry

from nextgis_connect.legacy.ngw.core.ngw_resource import NGWResource
from nextgis_connect.legacy.ngw_connection.application.connections_manager import (
    NgwConnectionsManager,
)

from .ngw_resource import dict_to_object


class NGWTileset(NGWResource):
    type_id = "tileset"
    type_title = "NGW Tileset"

    def _construct(self):
        super()._construct()
        self.wfs = dict_to_object(self._json[self.type_id])

    @property
    def layer_params(self) -> Tuple[str, str, str]:
        connections_manager = NgwConnectionsManager()
        connection = connections_manager.connection(self.connection_id)
        assert connection is not None

        # layer_info = self._json[self.type_id]

        url = (
            f"{connection.url}/api/component/render/tile?"
            f"resource={self.resource_id}&nd=204&z={{z}}&x={{x}}&y={{y}}"
        )

        params = {"type": "xyz", "url": url}

        connection.update_uri_config(params)

        params = {
            key: value for key, value in params.items() if value is not None
        }

        provider_metadata = QgsProviderRegistry.instance().providerMetadata(
            "wms"
        )
        return provider_metadata.encodeUri(params), self.display_name, "wms"
