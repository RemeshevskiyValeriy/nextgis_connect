from unittest.mock import MagicMock, call

import pytest
from qgis.PyQt.QtWidgets import QAction

from nextgis_connect.platform.qgis.compat import LayerType
from nextgis_connect.platform.qgis.layer_tree_action_registry import (
    LayerTreeActionRegistry,
)


class TestLayerTreeActionRegistry:
    def test_removes_each_registration_of_the_same_action(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        iface = MagicMock()
        action = QAction()
        registry = LayerTreeActionRegistry(iface)

        registry.register(
            action,
            "NextGIS Connect",
            LayerType.Vector,
            all_layers=True,
        )
        registry.register(
            action,
            "NextGIS Connect",
            LayerType.Raster,
            all_layers=True,
        )

        registry.clear()

        assert iface.addCustomActionForLayerType.call_count == 2
        assert iface.removeCustomActionForLayerType.call_args_list == [
            call(action),
            call(action),
        ]
        assert registry.registration_count == 0

        action.deleteLater()

    def test_clear_is_idempotent(self, qgis_app) -> None:
        del qgis_app
        iface = MagicMock()
        registry = LayerTreeActionRegistry(iface)

        registry.clear()
        registry.clear()

        iface.removeCustomActionForLayerType.assert_not_called()

    def test_clear_continues_after_removal_error(self, qgis_app) -> None:
        del qgis_app
        iface = MagicMock()
        first_action = QAction()
        second_action = QAction()
        registry = LayerTreeActionRegistry(iface)
        registry.register(
            first_action,
            "NextGIS Connect",
            LayerType.Vector,
            all_layers=True,
        )
        registry.register(
            second_action,
            "NextGIS Connect",
            LayerType.Raster,
            all_layers=True,
        )
        iface.removeCustomActionForLayerType.side_effect = (
            RuntimeError("Removal failed"),
            None,
        )

        with pytest.raises(RuntimeError, match="Removal failed"):
            registry.clear()

        assert iface.removeCustomActionForLayerType.call_args_list == [
            call(second_action),
            call(first_action),
        ]
        assert registry.registration_count == 0

        registry.clear()
        assert iface.removeCustomActionForLayerType.call_count == 2

        first_action.deleteLater()
        second_action.deleteLater()
