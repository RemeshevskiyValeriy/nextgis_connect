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

from qgis.core import QgsVectorLayer

from nextgis_connect.legacy.detached_editing.container.ui.layer_config_widget import (
    DetachedLayerConfigErrorPage,
    DetachedLayerConfigWidgetFactory,
)
from tests.ng_connect_testcase import NgConnectTestCase


class TestDetachedLayerConfigWidgetFactory(NgConnectTestCase):
    def test_supports_detached_layer_with_broken_metadata(self) -> None:
        layer_path = self.create_temp_file(".gpkg")
        layer = QgsVectorLayer(str(layer_path), "broken_container", "ogr")
        layer.setCustomProperty("ngw_is_detached_layer", True)
        factory = DetachedLayerConfigWidgetFactory()

        try:
            self.assertTrue(factory.supportsLayer(layer))

            widget = factory.createWidget(layer, None)
            try:
                self.assertIsInstance(widget, DetachedLayerConfigErrorPage)
            finally:
                widget.deleteLater()
        finally:
            layer.deleteLater()
