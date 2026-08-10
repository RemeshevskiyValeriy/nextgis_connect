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
from qgis.PyQt.QtWidgets import QMessageBox, QTreeView

from nextgis_connect.legacy.shell.presentation.dock import ng_connect_dock
from nextgis_connect.legacy.shell.presentation.dock.ng_connect_dock import (
    NgConnectDock,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModelBase
from nextgis_connect.legacy.tree_widget.proxy_model import NgConnectProxyModel
from nextgis_connect.platform.qgis import utils
from nextgis_connect.platform.qgis.errors import NgwError


class _FakeSignal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)


class _FakeModelResponse:
    def __init__(self) -> None:
        self.done = _FakeSignal()


class _FakeSelectionModel:
    def __init__(self, current_index) -> None:
        self._current_index = current_index

    def currentIndex(self):
        return self._current_index


class _FakeTreeView:
    def __init__(self, current_index) -> None:
        self._selection_model = _FakeSelectionModel(current_index)
        self.current_index = None

    def selectionModel(self) -> _FakeSelectionModel:
        return self._selection_model

    def setCurrentIndex(self, index) -> None:
        self.current_index = index


class _FakeProxyModel:
    def __init__(self, source_index) -> None:
        self._source_index = source_index

    def mapToSource(self, index):
        del index
        return self._source_index

    def mapFromSource(self, index):
        return ("proxy", index)


class _FakeSourceIndex:
    def __init__(self, resource) -> None:
        self._resource = resource

    def data(self, role):
        assert role == QNGWResourceItem.NGWResourceRole
        return self._resource


class _FakeButton:
    def __init__(self) -> None:
        self.text = None

    def setText(self, text: str) -> None:
        self.text = text


class _FakeMessageBox:
    Icon = QMessageBox.Icon
    StandardButton = QMessageBox.StandardButton
    next_result = QMessageBox.StandardButton.Yes
    last = None

    def __init__(self, parent=None) -> None:
        self.parent = parent
        self.icon = None
        self.window_title = None
        self.text = None
        self.text_format = None
        self.standard_buttons = None
        self.default_button = None
        self.buttons = {
            QMessageBox.StandardButton.Yes: _FakeButton(),
            QMessageBox.StandardButton.Cancel: _FakeButton(),
        }
        _FakeMessageBox.last = self

    def setIcon(self, icon) -> None:
        self.icon = icon

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def setText(self, text: str) -> None:
        self.text = text

    def setTextFormat(self, text_format) -> None:
        self.text_format = text_format

    def setStandardButtons(self, buttons) -> None:
        self.standard_buttons = buttons

    def setDefaultButton(self, button) -> None:
        self.default_button = button

    def button(self, button):
        return self.buttons[button]

    def exec(self):
        return self.next_result


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


def test_create_web_map_for_layer_cancel_without_styles_does_not_start_job(
    qgis_app,
) -> None:
    del qgis_app

    resource = SimpleNamespace(
        type_id=ng_connect_dock.NGWVectorLayer.type_id,
        display_name="Layer",
        get_children=list,
    )
    dock, _, _, create_calls = _web_map_dock(
        resource,
        should_create_default_style=False,
    )

    NgConnectDock.create_web_map_for_layer(dock)

    assert create_calls == []


def test_create_web_map_for_layer_accepts_default_style_creation(
    qgis_app,
) -> None:
    del qgis_app

    resource = SimpleNamespace(
        type_id=ng_connect_dock.NGWVectorLayer.type_id,
        display_name="Layer",
        get_children=list,
    )
    dock, source_index, response, create_calls = _web_map_dock(
        resource,
        should_create_default_style=True,
    )

    NgConnectDock.create_web_map_for_layer(dock)

    assert create_calls == [(source_index, None)]
    assert dock.create_map_response is response
    assert len(response.done.callbacks) == 2


def test_default_style_confirmation_uses_create_and_cancel_buttons(
    monkeypatch,
) -> None:
    monkeypatch.setattr(ng_connect_dock, "QMessageBox", _FakeMessageBox)
    dock = SimpleNamespace(tr=lambda text: text)

    _FakeMessageBox.next_result = QMessageBox.StandardButton.Yes
    confirm_default_style = (
        NgConnectDock._NgConnectDock__confirm_create_default_style_for_web_map
    )
    result = confirm_default_style(dock, "Layer")

    box = _FakeMessageBox.last
    assert result is True
    assert box is not None
    assert box.window_title == "Create Web map for layer"
    assert 'Layer "Layer" has no styles.' in box.text
    assert box.default_button == QMessageBox.StandardButton.Cancel
    assert (
        box.buttons[QMessageBox.StandardButton.Yes].text
        == "Create default style"
    )

    _FakeMessageBox.next_result = QMessageBox.StandardButton.Cancel

    result = confirm_default_style(dock, "Layer")

    assert result is False


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


def _web_map_dock(
    resource,
    *,
    should_create_default_style: bool,
):
    source_index = _FakeSourceIndex(resource)
    proxy_index = object()
    response = _FakeModelResponse()
    create_calls = []

    def create_map_for_layer(index, style_id):
        create_calls.append((index, style_id))
        return response

    dock = SimpleNamespace(
        proxy_model=_FakeProxyModel(source_index),
        resources_tree_view=_FakeTreeView(proxy_index),
        resource_model=SimpleNamespace(createMapForLayer=create_map_for_layer),
        open_create_web_map=lambda index: None,
        tr=lambda text: text,
        _NgConnectDock__layer_style_children=lambda resource: [],
        _NgConnectDock__confirm_create_default_style_for_web_map=(
            lambda layer_name: should_create_default_style
        ),
    )
    return dock, source_index, response, create_calls
