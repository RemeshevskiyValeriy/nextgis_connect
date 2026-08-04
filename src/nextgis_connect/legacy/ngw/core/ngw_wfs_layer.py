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

from qgis.core import QgsDataSourceUri

from nextgis_connect.legacy.ngw.core.ngw_abstract_vector_resource import (
    NGWAbstractVectorResource,
)
from nextgis_connect.legacy.ngw.core.ngw_wfs_connection import NGWWfsConnection

from .ngw_resource import dict_to_object


class NGWWfsLayer(NGWAbstractVectorResource):
    type_id = "wfsclient_layer"
    type_title = "NGW WFS Layer"

    @property
    def service_resource_id(self) -> int:
        return self._json[self.type_id]["connection"]["id"]

    def _construct(self):
        super()._construct()
        self.wfs = dict_to_object(self._json[self.type_id])

    def layer_params(
        self, wfs_connection: NGWWfsConnection
    ) -> Tuple[str, str, str]:
        uri = QgsDataSourceUri()

        uri.setParam("url", wfs_connection.wfs.path)
        uri.setUsername(wfs_connection.wfs.username)
        uri.setPassword(wfs_connection.wfs.password)
        uri.setParam("version", wfs_connection.wfs.version)

        uri.setParam("typename", self.wfs.layer_name)
        uri.setParam("srsname", f"EPSG:{self.wfs.geometry_srid}")
        uri.setParam("restrictToRequestBBOX", "1")

        return (uri.uri(False), self.display_name, "WFS")
