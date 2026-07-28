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
