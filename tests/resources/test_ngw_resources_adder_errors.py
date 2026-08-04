from typing import ClassVar, List
from unittest import mock

import pytest
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtWidgets import QMessageBox

from nextgis_connect.legacy import ngw_resources_adder as adder_module
from nextgis_connect.legacy.ngw.core import NGWWebMap
from nextgis_connect.legacy.ngw.core.ngw_webmap import NGWWebMapLayer
from nextgis_connect.legacy.ngw_resources_adder import NgwResourcesAdder
from nextgis_connect.platform.qgis.errors import ResourcePermissionError


class _ResourceModelProbe(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.forbidden_resource_ids = set()
        self.resources = {}

    def is_forbidden(self, resource_id: int) -> bool:
        return resource_id in self.forbidden_resource_ids

    def resource(self, resource_id: int):
        return self.resources.get(resource_id)


class _FakeButton:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class _FakeCheckBox:
    def __init__(self, text: str) -> None:
        self.text = text
        self.checked = True

    def isChecked(self) -> bool:
        return self.checked


class _FakeMessageBox:
    Icon = QMessageBox.Icon
    StandardButton = QMessageBox.StandardButton
    StandardButtons = QMessageBox.StandardButtons
    instances: ClassVar[List["_FakeMessageBox"]] = []

    def __init__(self) -> None:
        self.window_title = ""
        self.text = ""
        self.informative_text = ""
        self.detailed_text = ""
        self.checkbox = None
        self.buttons = {
            QMessageBox.StandardButton.Ignore: _FakeButton(),
            QMessageBox.StandardButton.Cancel: _FakeButton(),
        }
        _FakeMessageBox.instances.append(self)

    def setWindowTitle(self, title: str) -> None:
        self.window_title = title

    def setIcon(self, icon) -> None:
        del icon

    def setText(self, text: str) -> None:
        self.text = text

    def setInformativeText(self, text: str) -> None:
        self.informative_text = text

    def setDetailedText(self, text: str) -> None:
        self.detailed_text = text

    def setStandardButtons(self, buttons) -> None:
        del buttons

    def button(self, button):
        return self.buttons[button]

    def setDefaultButton(self, button) -> None:
        del button

    def setCheckBox(self, checkbox) -> None:
        self.checkbox = checkbox

    def exec(self):
        return QMessageBox.StandardButton.Ignore


def _insertion_point():
    return (
        QgsProject.instance().layerTreeRegistryBridge().layerInsertionPoint()
    )


def _webmap() -> NGWWebMap:
    resource_factory = mock.Mock()
    resource_factory.connection.server_url = "https://example.nextgis.com/"
    return NGWWebMap(
        resource_factory,
        {
            "resource": {
                "id": 265,
                "cls": NGWWebMap.type_id,
                "display_name": "Map",
                "description": None,
                "parent": None,
                "owner_user": None,
                "children": False,
                "interfaces": [],
            },
            "webmap": {"root_item": {"children": []}},
        },
    )


def test_webmap_permission_error_names_inaccessible_layer(qgis_app) -> None:
    del qgis_app

    model = _ResourceModelProbe()
    model.forbidden_resource_ids.add(164)
    adder = NgwResourcesAdder(model, [], _insertion_point())
    webmap_layer = NGWWebMapLayer(
        264,
        "Restricted roads",
        is_visible=True,
        transparency=None,
        legend=False,
        style_parent_id=164,
    )

    with pytest.raises(ResourcePermissionError) as error_info:
        adder._NgwResourcesAdder__collect_params_for_webmap_layer(
            _webmap(),
            webmap_layer,
        )

    error = error_info.value
    assert "Restricted roads" in error.user_message
    assert "164" in (error.detail or "")
    assert "Restricted roads" in error.log_message


def test_webmap_missing_resources_ignores_forbidden_ids(qgis_app) -> None:
    del qgis_app

    model = _ResourceModelProbe()
    model.forbidden_resource_ids.add(164)
    adder = NgwResourcesAdder(model, [], _insertion_point())
    webmap = mock.Mock(spec=NGWWebMap)
    webmap.all_resources_id = [164]
    index = mock.Mock()
    index.data.return_value = webmap

    missing_resources = (
        adder._NgwResourcesAdder__missing_resources_from_webmap(index)
    )

    assert missing_resources == []


def test_batch_adding_error_dialog_can_skip_and_apply_to_all(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    _FakeMessageBox.instances = []
    monkeypatch.setattr(adder_module, "QMessageBox", _FakeMessageBox)
    monkeypatch.setattr(adder_module, "QCheckBox", _FakeCheckBox)

    model = _ResourceModelProbe()
    adder = NgwResourcesAdder(model, [], _insertion_point())
    adder._NgwResourcesAdder__is_mass_adding = True
    context = adder_module._ResourceAddingErrorContext(
        display_name="Restricted roads",
        insertion_id=123,
        resource_ids=(164,),
        resource_url="https://example.nextgis.com/resource/164",
    )

    is_skipped = adder._NgwResourcesAdder__skip_after_adding_error(
        ResourcePermissionError(user_message="No access"),
        context,
    )

    assert is_skipped is True
    assert adder._NgwResourcesAdder__skip_future_adding_errors is True
    assert 123 in adder._NgwResourcesAdder__skipped_resources
    assert 164 in adder._NgwResourcesAdder__skipped_resources
    assert len(_FakeMessageBox.instances) == 1
    assert "Restricted roads" in _FakeMessageBox.instances[0].text
    assert _FakeMessageBox.instances[0].checkbox.text == "Apply to all"
    assert (
        _FakeMessageBox.instances[0]
        .buttons[QMessageBox.StandardButton.Ignore]
        .text
        == "Skip"
    )
    assert (
        _FakeMessageBox.instances[0]
        .buttons[QMessageBox.StandardButton.Cancel]
        .text
        == "Cancel"
    )

    second_context = adder_module._ResourceAddingErrorContext(
        display_name="Restricted buildings",
        insertion_id=124,
        resource_ids=(165,),
    )
    is_second_skipped = adder._NgwResourcesAdder__skip_after_adding_error(
        RuntimeError("Second error"),
        second_context,
    )

    assert is_second_skipped is True
    assert 124 in adder._NgwResourcesAdder__skipped_resources
    assert 165 in adder._NgwResourcesAdder__skipped_resources
    assert len(_FakeMessageBox.instances) == 1
