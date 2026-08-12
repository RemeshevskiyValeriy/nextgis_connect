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
from typing import Any, List, Tuple
from unittest import mock

import pytest
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QModelIndex, QObject, pyqtSignal
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import (
    QAbstractButton,
    QDialog,
    QDialogButtonBox,
)

from nextgis_connect.legacy.ngw.core.ngw_qgis_style import NGWQGISVectorStyle
from nextgis_connect.legacy.ngw.core.ngw_resource_creator import (
    ResourceCreator,
)
from nextgis_connect.legacy.ngw.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    NgwServerFeature,
)
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job import (
    NGWCreateVectorLayer,
)
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job_error import (
    JobError,
)
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
        self._is_enabled = True

    def isChecked(self) -> bool:
        return self._is_checked

    def setChecked(self, is_checked: bool) -> None:
        self._is_checked = is_checked

    def isEnabled(self) -> bool:
        return self._is_enabled

    def setEnabled(self, is_enabled: bool) -> None:
        self._is_enabled = is_enabled


class _ComboBox:
    def __init__(self, current_data: Any) -> None:
        self._current_data = current_data
        self._tooltip = ""

    def currentData(self) -> Any:
        return self._current_data

    def setToolTip(self, tooltip: str) -> None:
        self._tooltip = tooltip

    def toolTip(self) -> str:
        return self._tooltip


class _GeometryComboBox(_ComboBox):
    def __init__(self) -> None:
        super().__init__(None)
        self._items: List[Any] = []

    def addItem(self, *arguments: Any) -> None:
        self._items.append(arguments[-1])

    def findData(self, data: Any) -> int:
        try:
            return self._items.index(data)
        except ValueError:
            return -1

    def setCurrentIndex(self, index: int) -> None:
        self._current_data = self._items[index]


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


def test_build_resource_adds_created_by_metadata(qgis_app) -> None:
    del qgis_app

    dialog, _ = _creation_dialog()

    with mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator"
        ".ResourceCreator._plugin_version",
        return_value="4.0.0",
    ):
        resource = dialog._VectorLayerCreationDialog__build_resource()

    assert resource["resmeta"] == {
        "items": {"created_by": "NextGIS-Connect/4.0.0"}
    }

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


def test_build_resource_creates_layer_without_geometry(qgis_app) -> None:
    del qgis_app

    dialog, _ = _creation_dialog(
        geometry_type=WkbType.NoGeometry,
        include_z=True,
    )

    resource = dialog._VectorLayerCreationDialog__build_resource()

    assert resource["vector_layer"] == {
        "geometry_type": "NONE",
        "fields": [],
    }

    dialog.deleteLater()


def test_enable_no_geometry_type_disables_z_checkbox(qgis_app) -> None:
    del qgis_app

    dialog = VectorLayerCreationDialog.__new__(VectorLayerCreationDialog)
    dialog.geometry_combobox = _GeometryComboBox()
    dialog.z_checkbox = _CheckBox(True)
    dialog._VectorLayerCreationDialog__has_no_geometry_support = False

    dialog.enable_no_geometry_layer_type()
    no_geometry_index = dialog.geometry_combobox.findData(
        int(WkbType.NoGeometry)
    )

    assert no_geometry_index >= 0

    dialog.geometry_combobox.setCurrentIndex(no_geometry_index)
    dialog._VectorLayerCreationDialog__update_geometry_controls()

    assert not dialog.z_checkbox.isEnabled()
    assert not dialog.z_checkbox.isChecked()


def test_update_field_type_tooltip_handles_empty_combo_data(qgis_app) -> None:
    del qgis_app

    dialog = VectorLayerCreationDialog.__new__(VectorLayerCreationDialog)
    QDialog.__init__(dialog)
    dialog.field_type_combobox = _ComboBox("")

    dialog._VectorLayerCreationDialog__update_field_type_tooltip()

    assert dialog.field_type_combobox.toolTip() == (
        "Select attribute value type."
    )

    dialog.deleteLater()


def test_create_no_geometry_versioned_layer_requires_dev8(qgis_app) -> None:
    del qgis_app

    parent_resource = mock.Mock()
    parent_resource.connection.has_support_for_feature.return_value = False
    vector_layer = {
        "feature_layer": {
            "versioning": {
                "enabled": True,
            },
        },
        "vector_layer": {
            "geometry_type": "NONE",
        },
    }
    job = NGWCreateVectorLayer(parent_resource, vector_layer)

    with pytest.raises(JobError, match=r"5\.5\.0\.dev8"):
        job._do()

    parent_resource.connection.has_support_for_feature.assert_called_once_with(
        NgwServerFeature.NO_GEOMETRY_LAYER_VERSIONING
    )
    parent_resource.get_api_collection_url.assert_not_called()


def test_create_vector_layer_job_creates_default_style(qgis_app) -> None:
    del qgis_app

    parent_resource = mock.Mock()
    vector_resource = mock.Mock()
    style_resource = mock.Mock()
    vector_layer = {
        "vector_layer": {
            "geometry_type": "POINT",
        },
    }

    with mock.patch.object(
        ResourceCreator,
        "create_empty_vector_layer",
        return_value=vector_resource,
    ) as create_vector_layer, mock.patch.object(
        ResourceCreator,
        "create_default_vector_style",
        return_value=style_resource,
    ) as create_default_style:
        job = NGWCreateVectorLayer(parent_resource, vector_layer)
        job._do()

    create_vector_layer.assert_called_once_with(parent_resource, vector_layer)
    create_default_style.assert_called_once_with(vector_resource)
    assert job.result.added_resources == [vector_resource, style_resource]
    assert job.result.main_resource_id == vector_resource.resource_id
    parent_resource.update.assert_called_once_with()


def test_create_default_vector_style_posts_expected_payload() -> None:
    connection = mock.Mock()
    connection.post.return_value = {"id": 100}
    display_name = QgsApplication.translate(
        "ResourceCreator",
        "Default style",
    )

    resource_factory = mock.Mock()
    resource_factory.connection = connection

    vector_resource = mock.Mock(spec=NGWVectorLayer)
    vector_resource.resource_id = 99
    vector_resource.res_factory = resource_factory
    vector_resource.common = SimpleNamespace(children=False)
    vector_resource.get_api_collection_url.return_value = "/api/resource/"

    style_json = {
        "resource": {
            "id": 100,
            "cls": NGWQGISVectorStyle.type_id,
            "parent": {"id": 99},
            "owner_user": None,
            "children": False,
            "display_name": display_name,
            "description": "",
            "interfaces": [],
        },
    }

    with mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator.NGWResource"
        ".receive_resource_obj",
        return_value=style_json,
    ) as receive_resource:
        style_resource = ResourceCreator.create_default_vector_style(
            vector_resource
        )

    connection.post.assert_called_once_with(
        "/api/resource/",
        params={
            "resource": {
                "cls": NGWQGISVectorStyle.type_id,
                "parent": {"id": 99},
                "display_name": display_name,
            },
        },
        feedback=None,
    )
    receive_resource.assert_called_once_with(
        connection,
        100,
        feedback=None,
    )
    assert isinstance(style_resource, NGWQGISVectorStyle)
    assert vector_resource.common.children is True


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


def test_upload_vector_layer_sends_creation_metadata() -> None:
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
            metadata={
                "created_by": "NextGIS-Connect/4.0.0",
                "source": "/project/layer.gpkg|layername=places",
            },
        )

    params = connection.post.call_args.kwargs["params"]

    assert params["resmeta"] == {
        "items": {
            "created_by": "NextGIS-Connect/4.0.0",
            "source": "/project/layer.gpkg|layername=places",
        }
    }


def test_resource_creation_metadata_uses_sanitized_layer_source() -> None:
    layer = mock.Mock()
    with mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator"
        ".ResourceCreator._plugin_version",
        return_value="4.0.0",
    ), mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator"
        ".QgisLayerSourceSanitizer"
    ) as sanitizer_class:
        sanitizer_class.return_value.sanitize.return_value = (
            "roads.gpkg|layername=places"
        )

        metadata = ResourceCreator.resource_creation_metadata(layer)

    assert metadata == {
        "created_by": "NextGIS-Connect/4.0.0",
        "source": "roads.gpkg|layername=places",
    }
    sanitizer_class.return_value.sanitize.assert_called_once_with(layer)


def test_resource_creation_metadata_omits_unknown_source() -> None:
    layer = mock.Mock()
    with mock.patch.object(
        ResourceCreator,
        "resource_created_by_metadata",
        return_value={"created_by": "NextGIS-Connect/4.0.0"},
    ), mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator"
        ".QgisLayerSourceSanitizer"
    ) as sanitizer_class:
        sanitizer_class.return_value.sanitize.return_value = None

        metadata = ResourceCreator.resource_creation_metadata(layer)

    assert metadata == {"created_by": "NextGIS-Connect/4.0.0"}


def test_disabled_creation_metadata_does_not_sanitize_source() -> None:
    layer = mock.Mock()
    with mock.patch.object(
        ResourceCreator,
        "resource_created_by_metadata",
        return_value={},
    ), mock.patch(
        "nextgis_connect.legacy.ngw.core.ngw_resource_creator"
        ".QgisLayerSourceSanitizer"
    ) as sanitizer_class:
        metadata = ResourceCreator.resource_creation_metadata(layer)

    assert metadata == {}
    sanitizer_class.assert_not_called()


def test_upload_vector_layer_skips_empty_creation_metadata() -> None:
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
            metadata={},
        )

    params = connection.post.call_args.kwargs["params"]

    assert "resmeta" not in params


def _creation_dialog(
    versioning_mode: VersioningMode = VersioningMode.AUTO,
    geometry_type: WkbType = WkbType.Point,
    include_z: bool = False,
) -> Tuple[VectorLayerCreationDialog, LoadingPushButton]:
    dialog = VectorLayerCreationDialog.__new__(VectorLayerCreationDialog)
    QDialog.__init__(dialog)
    resources_model, parent_index = _resources_model()

    dialog.layer_name_lineedit = _LineEdit("Created layer")
    dialog.fields_view = _FieldsView()
    dialog.versioning_combobox = _ComboBox(versioning_mode.value)
    dialog.geometry_combobox = _ComboBox(int(geometry_type))
    dialog.z_checkbox = _CheckBox(include_z)
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
