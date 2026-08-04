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

from types import SimpleNamespace
from unittest.mock import MagicMock

from qgis.core import QgsProviderRegistry

from nextgis_connect.legacy.ngw.core import ngw_wms_service
from nextgis_connect.legacy.ngw.core.ngw_wms_service import NGWWmsService
from nextgis_connect.platform.qgis.wms_uri import QgisWmsUriFactory


class TestQgisWmsUriFactory:
    def test_creates_qgis_ui_compatible_uri(self, qgis_app) -> None:
        del qgis_app

        uri = QgisWmsUriFactory.create(
            {
                "authcfg": "zs6c64z",
                "crs": "EPSG:3857",
                "format": "image/png",
                "layers": "ngw_id_7016",
                "styles": "",
                "url": "https://example.nextgis.com/api/resource/7171/wms",
            }
        )
        parameters = (
            QgsProviderRegistry.instance()
            .providerMetadata("wms")
            .decodeUri(uri)
        )

        assert parameters["authcfg"] == "zs6c64z"
        assert parameters["contextualWMSLegend"] == "0"
        assert parameters["crs"] == "EPSG:3857"
        assert parameters["dpiMode"] == "7"
        assert parameters["featureCount"] == "10"
        assert parameters["format"] == "image/png"
        assert parameters["layers"] == "ngw_id_7016"
        assert parameters["tilePixelRatio"] == "0"
        assert parameters["url"] == (
            "https://example.nextgis.com/api/resource/7171/wms"
        )
        assert "styles" in parameters
        assert "styles" in uri.split("&")
        assert "styles=" not in uri.split("&")

    def test_ngw_wms_service_layer_params_use_qgis_defaults(
        self,
        qgis_app,
        monkeypatch,
    ) -> None:
        del qgis_app
        service = MagicMock(spec=NGWWmsService)
        service.layers = [object()]
        service.connection_id = "connection-id"
        service.get_absolute_api_url.return_value = (
            "https://example.nextgis.com/api/resource/7171"
        )
        connection = MagicMock()
        connection.update_uri_config.side_effect = lambda uri_params: (
            uri_params.update({"authcfg": "zs6c64z"})
        )
        connections_manager = MagicMock()
        connections_manager.connection.return_value = connection
        monkeypatch.setattr(
            ngw_wms_service,
            "NgwConnectionsManager",
            lambda: connections_manager,
        )
        layer = SimpleNamespace(
            keyname="ngw_id_7016",
            display_name="Test WMS layer",
        )

        uri, name, provider_key = NGWWmsService.params_for_layer(
            service,
            layer,
        )
        parameters = (
            QgsProviderRegistry.instance()
            .providerMetadata("wms")
            .decodeUri(uri)
        )

        assert name == "Test WMS layer"
        assert provider_key == "wms"
        assert parameters["authcfg"] == "zs6c64z"
        assert parameters["contextualWMSLegend"] == "0"
        assert parameters["dpiMode"] == "7"
        assert parameters["featureCount"] == "10"
        assert parameters["tilePixelRatio"] == "0"
        assert parameters["url"] == (
            "https://example.nextgis.com/api/resource/7171/wms"
        )
