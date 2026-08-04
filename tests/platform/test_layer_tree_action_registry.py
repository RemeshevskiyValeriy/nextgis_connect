from unittest.mock import MagicMock, call

import pytest
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtWidgets import QAction, QMenu

from nextgis_connect.platform.qgis.compat import LayerType
from nextgis_connect.platform.qgis.layer_tree_action_registry import (
    LayerTreeActionRegistry,
)


class _Signal:
    def __init__(self) -> None:
        self.slots = []

    def connect(self, slot) -> None:
        self.slots.append(slot)

    def disconnect(self, slot) -> None:
        self.slots.remove(slot)

    def emit(self, *args) -> None:
        for slot in tuple(self.slots):
            slot(*args)


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

    def test_applies_registered_menu_icon_before_context_menu_show(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        iface = MagicMock()
        layer_tree_view = MagicMock()
        layer_tree_view.contextMenuAboutToShow = _Signal()
        iface.layerTreeView.return_value = layer_tree_view
        action = QAction()
        menu_icon = QIcon(QPixmap(16, 16))
        registry = LayerTreeActionRegistry(iface)

        registry.register(
            action,
            "NextGIS Connect",
            LayerType.Vector,
            all_layers=True,
            menu_icon=menu_icon,
        )

        context_menu = QMenu()
        plugin_menu = QMenu("NextGIS Connect", context_menu)
        context_menu.addMenu(plugin_menu)
        plugin_menu_action = context_menu.actions()[0]

        assert plugin_menu_action.icon().isNull()

        layer_tree_view.contextMenuAboutToShow.emit(context_menu)

        assert plugin_menu_action.icon().cacheKey() == menu_icon.cacheKey()
        assert plugin_menu_action.isIconVisibleInMenu()

        registry.clear()

        assert layer_tree_view.contextMenuAboutToShow.slots == []

        action.deleteLater()
        context_menu.deleteLater()
