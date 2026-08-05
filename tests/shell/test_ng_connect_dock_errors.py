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

import pytest
import qgis.utils
from qgis.core import Qgis, QgsLayerTreeLayer, QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QModelIndex
from qgis.PyQt.QtWidgets import QTreeView

from nextgis_connect.legacy.shell.presentation.dock import ng_connect_dock
from nextgis_connect.legacy.shell.presentation.dock.ng_connect_dock import (
    NgConnectDock,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModelBase
from nextgis_connect.legacy.tree_widget.proxy_model import NgConnectProxyModel
from nextgis_connect.platform.qgis import utils
from nextgis_connect.platform.qgis.errors import NgwError


@pytest.mark.parametrize("job_name", [None, ""])
def test_reset_model_error_stops_root_loading(job_name) -> None:
    calls = []
    error = NgwError("Connection error", is_network_problem=True)
    dock = SimpleNamespace(
        _NgConnectDock__root_children_loading_parent_id=None,
        _NgConnectDock__root_loading_cancel_requested=False,
        unblock_gui=lambda: calls.append("unblock"),
        _NgConnectDock__show_root_loading_error=lambda exception: calls.append(
            ("root_error", exception)
        ),
    )
    process_exception = NgConnectDock._NgConnectDock__model_exception_process

    process_exception(
        dock,
        job_name,
        "",
        error,
        Qgis.MessageLevel.Critical,
    )

    assert calls == ["unblock", ("root_error", error)]


def test_create_group_cancel_refreshes_lazy_parent_branch(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    model = QNGWResourceTreeModelBase()
    model.support_status = utils.SupportStatus.SUPPORTED
    resource = SimpleNamespace(
        display_name="Group",
        common=SimpleNamespace(cls="resource_group", children=True),
        icon_path="",
        resource_id=1,
        type_id="resource_group",
        connection=SimpleNamespace(server_url=""),
        children_count=None,
    )
    item = QNGWResourceItem(resource)
    model.root_item.addChild(item)
    source_index = model.index(0, 0, QModelIndex())

    proxy_model = NgConnectProxyModel(None)
    proxy_model.setSourceModel(model)
    tree_view = QTreeView()
    tree_view.setModel(proxy_model)
    proxy_index = proxy_model.mapFromSource(source_index)
    tree_view.setCurrentIndex(proxy_index)

    refreshed_indexes = []

    def refresh_lazy_children_state(index: QModelIndex) -> None:
        refreshed_indexes.append(index)

    def fail_create_group(*args, **kwargs) -> None:
        del args
        del kwargs
        raise AssertionError("Create group job must not start after cancel")

    monkeypatch.setattr(
        ng_connect_dock.QInputDialog,
        "getText",
        lambda *args, **kwargs: ("", False),
    )
    monkeypatch.setattr(
        model,
        "refresh_lazy_children_state",
        refresh_lazy_children_state,
    )
    monkeypatch.setattr(
        model,
        "tryCreateNGWGroup",
        fail_create_group,
        raising=False,
    )
    dock = SimpleNamespace(
        proxy_model=proxy_model,
        resources_tree_view=tree_view,
        resource_model=model,
        show_info=lambda message: None,
        tr=lambda text: text,
    )

    NgConnectDock.create_group(dock)

    assert len(refreshed_indexes) == 1
    assert refreshed_indexes[0].internalPointer() is item
    assert tree_view.currentIndex() == proxy_index

    tree_view.deleteLater()
    proxy_model.deleteLater()


def test_select_qgis_layers_selects_added_layers(qgis_app) -> None:
    del qgis_app

    project = QgsProject.instance()
    first_layer = QgsVectorLayer("Point?crs=EPSG:4326", "First", "memory")
    second_layer = QgsVectorLayer("Point?crs=EPSG:4326", "Second", "memory")
    project.addMapLayers([first_layer, second_layer])
    dock = NgConnectDock.__new__(NgConnectDock)
    dock.iface = qgis.utils.iface

    try:
        dock._NgConnectDock__select_qgis_layers(
            (first_layer.id(), second_layer.id())
        )

        layer_tree_view = qgis.utils.iface.layerTreeView()
        selected_layer_ids = {
            node.layerId()
            for node in layer_tree_view.selectedNodes()
            if isinstance(node, QgsLayerTreeLayer)
        }
        current_node = layer_tree_view.currentNode()

        assert selected_layer_ids == {first_layer.id(), second_layer.id()}
        assert isinstance(current_node, QgsLayerTreeLayer)
        assert current_node.layerId() == second_layer.id()
    finally:
        project.removeMapLayers([first_layer.id(), second_layer.id()])
