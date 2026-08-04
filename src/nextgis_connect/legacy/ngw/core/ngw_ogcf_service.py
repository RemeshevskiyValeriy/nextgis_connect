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

from qgis.core import QgsDataSourceUri

from nextgis_connect.legacy.ngw_connection.application.connections_manager import (
    NgwConnectionsManager,
)

from .ngw_resource import NGWResource, dict_to_object, list_dict_to_list_object


class NGWOgcfService(NGWResource):
    type_id = "ogcfserver_service"

    def _construct(self):
        super()._construct()
        # wfsserver_service
        self.ogcf = dict_to_object(self._json[self.type_id])
        if hasattr(self.ogcf, "collections"):
            self.layers = list_dict_to_list_object(self.ogcf.collections)
        else:
            self.layers = []

    def params_for_layer(self, layer):
        connections_manager = NgwConnectionsManager()
        connection = connections_manager.connection(self.connection_id)

        uri = QgsDataSourceUri()
        uri.setParam("typename", layer.keyname)
        uri.setParam("srsname", "OGC:CRS84")
        uri.setParam("preferCoordinatesForWfsT11", "false")
        uri.setParam("pagingEnabled", "false")
        uri.setParam("maxNumFeatures", str(layer.maxfeatures))
        uri.setParam("restrictToRequestBBOX", "1")
        uri.setParam("authcfg", connection.auth_config_id)
        uri.setParam("url", self.get_absolute_api_url() + "/ogcf")

        return (uri.uri(True), layer.display_name, "OAPIF")

    def get_layers(self):
        return self.ogcf.layers
