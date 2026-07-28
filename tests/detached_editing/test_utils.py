import unittest

from nextgis_connect.legacy.detached_editing import utils
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestDetachedLayerEditingUtils(NgConnectTestCase):
    def test_container_path(self) -> None:
        layer_path = self.data_path(TestData.Points)
        self.assertEqual(utils.container_path(layer_path), layer_path)
        self.assertEqual(
            utils.container_path(self.layer(TestData.Points)), layer_path
        )
        self.assertEqual(
            utils.container_path(f"{layer_path}|layername=points_layer"),
            layer_path,
        )

    def test_detached_layer_uri(self) -> None:
        layer_path = self.data_path(TestData.Points)
        layer_uri = self.layer_uri(TestData.Points)
        self.assertEqual(utils.detached_layer_uri(layer_path), layer_uri)

    @mock_container(TestData.Points)
    def test_detached_layer_uri_uses_context_metadata(
        self, container_mock, _qgs_layer
    ) -> None:
        self.assertEqual(
            utils.detached_layer_uri(container_mock.context),
            f"{container_mock.path}|layername="
            f"{container_mock.metadata.table_name}",
        )

    def test_is_ngw_container(self) -> None:
        with self.subTest("With path"):
            layer_path = self.data_path(TestData.Points)
            self.assertFalse(utils.is_ngw_container(layer_path))
            # TODO true

        with self.subTest("With layer"):
            layer = self.layer(TestData.Points)

            layer.setCustomProperty("ngw_is_detached_layer", True)
            self.assertTrue(utils.is_ngw_container(layer))
            layer.setCustomProperty("ngw_is_detached_layer", False)
            self.assertFalse(utils.is_ngw_container(layer))

    @mock_container(TestData.Points)
    def test_is_ngw_container_with_detached_container_path(
        self, container_mock, _qgs_layer
    ) -> None:
        self.assertTrue(utils.is_ngw_container(container_mock.path))

    def test_reset_container_properties(self) -> None:
        layer = self.layer(TestData.Points)

        layer.setCustomProperty("ngw_is_detached_layer", True)
        layer.setCustomProperty("ngw_connection_id", "connection")
        layer.setCustomProperty("ngw_instance_id", "instance")
        layer.setCustomProperty("ngw_resource_id", 1)

        utils.reset_container_properties(layer)

        self.assertIsNone(layer.customProperty("ngw_is_detached_layer"))
        self.assertIsNone(layer.customProperty("ngw_connection_id"))
        self.assertIsNone(layer.customProperty("ngw_instance_id"))
        self.assertIsNone(layer.customProperty("ngw_resource_id"))


if __name__ == "__main__":
    unittest.main()
