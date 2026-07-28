from typing import Any, List, Tuple
from unittest import mock

from qgis.PyQt.QtCore import QModelIndex, QObject, pyqtSignal
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QDialog,
    QDialogButtonBox,
)

from nextgis_connect.legacy.ngw.core.ngw_resource_creator import (
    ResourceCreator,
)
from nextgis_connect.legacy.ngw.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.legacy.ngw.resources.creation.vector_layer_creation_dialog import (
    VectorLayerCreationDialog,
    VersioningMode,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.platform.qgis.compat import WkbType
from nextgis_connect.ui_kit.buttons.loading import LoadingPushButton


class _CreateResourceResponse(QObject):
    done = pyqtSignal(QModelIndex)
    failed = pyqtSignal(object)
    finished = pyqtSignal()


class _LineEdit:
    def __init__(self, text: str) -> None:
        self._text = text

    def text(self) -> str:
        return self._text


class _CheckBox:
    def __init__(self, is_checked: bool) -> None:
        self._is_checked = is_checked

    def isChecked(self) -> bool:
        return self._is_checked


class _ComboBox:
    def __init__(self, current_data: Any) -> None:
        self._current_data = current_data

    def currentData(self) -> Any:
        return self._current_data


class _Fields:
    def to_json(self) -> List[dict]:
        return []


class _FieldsModel:
    fields = _Fields()


class _FieldsView:
    def model(self) -> _FieldsModel:
        return _FieldsModel()


def test_create_callback_accepts_dialog_after_response_done(qgis_app) -> None:
    del qgis_app

    dialog, create_button = _creation_dialog()
    response = _CreateResourceResponse()
    created_resources = []

    def create_resource(resource):
        created_resources.append(resource)
        return response

    dialog.set_create_resource_callback(create_resource)

    create_button.click()

    assert len(created_resources) == 1
    assert created_resources[0]["resource"]["cls"] == NGWVectorLayer.type_id
    assert created_resources[0]["resource"]["parent"]["id"] == 42
    assert dialog.resource == created_resources[0]
    assert create_button.is_loading()
    assert not _cancel_button(dialog).isEnabled()
    assert dialog.result() == QDialog.DialogCode.Rejected

    response.done.emit(QModelIndex())

    assert not create_button.is_loading()
    assert _cancel_button(dialog).isEnabled()
    assert dialog.result() == QDialog.DialogCode.Accepted

    dialog.deleteLater()


def test_create_callback_stops_loading_without_response(qgis_app) -> None:
    del qgis_app

    dialog, create_button = _creation_dialog()
    dialog.set_create_resource_callback(lambda _resource: None)

    create_button.click()

    assert not create_button.is_loading()
    assert _cancel_button(dialog).isEnabled()
    assert dialog.result() == QDialog.DialogCode.Rejected

    dialog.deleteLater()


def test_build_resource_omits_versioning_in_auto_mode(qgis_app) -> None:
    del qgis_app

    dialog, _ = _creation_dialog(VersioningMode.AUTO)

    resource = dialog._VectorLayerCreationDialog__build_resource()

    assert "versioning" not in resource["feature_layer"]

    dialog.deleteLater()


def test_build_resource_enables_versioning_explicitly(qgis_app) -> None:
    del qgis_app

    dialog, _ = _creation_dialog(VersioningMode.ENABLED)

    resource = dialog._VectorLayerCreationDialog__build_resource()

    assert resource["feature_layer"]["versioning"] == {"enabled": True}

    dialog.deleteLater()


def test_build_resource_disables_versioning_explicitly(qgis_app) -> None:
    del qgis_app

    dialog, _ = _creation_dialog(VersioningMode.DISABLED)

    resource = dialog._VectorLayerCreationDialog__build_resource()

    assert resource["feature_layer"]["versioning"] == {"enabled": False}

    dialog.deleteLater()


def test_upload_vector_layer_does_not_send_versioning_flag() -> None:
    connection = mock.Mock()
    connection.tus_upload_file.return_value = {"id": "upload"}
    connection.post.return_value = {"id": 99}

    parent_resource = mock.Mock()
    parent_resource.resource_id = 42
    parent_resource.res_factory.connection = connection
    parent_resource.get_api_collection_url.return_value = "/api/resource/"

    with mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator.NGWResource"
        ".receive_resource_obj",
        return_value=mock.Mock(),
    ), mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator.NGWVectorLayer",
        return_value=mock.Mock(),
    ):
        ResourceCreator.create_vector_layer(
            parent_resource,
            "/tmp/fake.gpkg",
            "Created layer",
            None,
            lambda *_args: None,
            lambda: None,
        )

    params = connection.post.call_args.kwargs["params"]

    assert "feature_layer" not in params


def _creation_dialog(
    versioning_mode: VersioningMode = VersioningMode.AUTO,
) -> Tuple[VectorLayerCreationDialog, LoadingPushButton]:
    dialog = VectorLayerCreationDialog.__new__(VectorLayerCreationDialog)
    QDialog.__init__(dialog)
    resources_model, parent_index = _resources_model()

    dialog.layer_name_lineedit = _LineEdit("Created layer")
    dialog.fields_view = _FieldsView()
    dialog.versioning_combobox = _ComboBox(versioning_mode.value)
    dialog.geometry_combobox = _ComboBox(int(WkbType.Point))
    dialog.z_checkbox = _CheckBox(False)
    dialog.add_to_project_checkbox = _CheckBox(True)
    dialog.button_box = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Cancel,
        dialog,
    )

    create_button = LoadingPushButton(parent=dialog)
    create_button.setEnabled(True)
    create_button.clicked.connect(
        dialog._VectorLayerCreationDialog__create_clicked
    )

    dialog._VectorLayerCreationDialog__resources_model = resources_model
    dialog._VectorLayerCreationDialog__parent_resource_index = parent_index
    dialog._VectorLayerCreationDialog__result_resource = None
    dialog._VectorLayerCreationDialog__create_resource = None
    dialog._VectorLayerCreationDialog__create_button = create_button
    dialog._VectorLayerCreationDialog__is_creating = False

    return dialog, create_button


def _resources_model() -> Tuple[QStandardItemModel, QModelIndex]:
    model = QStandardItemModel()
    parent_item = QStandardItem("Parent")
    parent_item.setData(42, QNGWResourceItem.NGWResourceIdRole)
    model.appendRow(parent_item)

    return model, model.index(0, 0)


def _cancel_button(dialog: VectorLayerCreationDialog) -> QAbstractButton:
    button = dialog.button_box.button(QDialogButtonBox.StandardButton.Cancel)
    assert button is not None
    return button
