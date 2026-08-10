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

from enum import Enum
from pathlib import Path
from typing import Any, Callable, ClassVar, Dict, List, Optional, cast

from qgis.core import (
    QgsWkbTypes,
)
from qgis.gui import QgsGui
from qgis.PyQt import uic
from qgis.PyQt.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QSize,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QKeyEvent
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QWidget,
)

from nextgis_connect.legacy.ngw.core.ngw_resource_creator import (
    ResourceCreator,
)
from nextgis_connect.legacy.ngw.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.legacy.ngw.resources.ngw_data_type_delegate import (
    NgwDataTypeDelegate,
)
from nextgis_connect.legacy.ngw.resources.ngw_field import NgwDataType
from nextgis_connect.legacy.ngw.resources.ngw_fields_model import (
    NgwFieldsModel,
)
from nextgis_connect.legacy.ngw.resources.utils import generate_unique_name
from nextgis_connect.legacy.settings.ng_connect_settings import (
    NgConnectSettings,
)
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.platform.qgis.compat import WkbType
from nextgis_connect.ui_kit.buttons.loading import LoadingPushButton
from nextgis_connect.ui_kit.delegates.checkbox_delegate import (
    CheckBoxDelegate,
)
from nextgis_connect.ui_kit.delegates.header_with_centered_icon_proxy_style import (
    HeaderWithCenteredIconProxyStyle,
)
from nextgis_connect.ui_kit.icons import qgis_icon, wkb_type_icon

VectorLayerCreationDialogBase, _ = uic.loadUiType(
    str(Path(__file__).parent / "vector_layer_creation_dialog_base.ui")
)


class VersioningMode(Enum):
    AUTO = "auto"
    ENABLED = "enabled"
    DISABLED = "disabled"


class VectorLayerCreationDialog(QDialog, VectorLayerCreationDialogBase):
    NO_GEOMETRY_TYPE = "NONE"
    SUPPORTED_WKB_TYPES: ClassVar[List[WkbType]] = [
        WkbType.Point,
        WkbType.LineString,
        WkbType.Polygon,
        WkbType.MultiPoint,
        WkbType.MultiLineString,
        WkbType.MultiPolygon,
    ]

    validity_changed = pyqtSignal(bool)

    __resources_model: QAbstractItemModel
    __parent_resource_index: QModelIndex

    def __init__(
        self,
        resources_model: QAbstractItemModel,
        parent_resource_index: QModelIndex,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.__resources_model = resources_model
        self.__parent_resource_index = parent_resource_index
        self.__result_resource = None
        self.__create_resource = None
        self.__create_button: Optional[LoadingPushButton] = None
        self.__is_creating = False
        self.__has_boolean_support = False
        self.__has_json_support = False
        self.__has_no_geometry_support = False
        self.__setup_ui()

    def accept(self) -> None:
        self.__result_resource = self.__build_resource()
        self.__save_creation_settings()
        return super().accept()

    def set_create_resource_callback(
        self,
        callback: Callable[[Dict[str, Any]], Optional[Any]],
    ) -> None:
        self.__create_resource = callback

    def __build_resource(self) -> Dict[str, Any]:
        parent_id = self.__resources_model.data(
            self.__parent_resource_index, QNGWResourceItem.NGWResourceIdRole
        )
        display_name = self.layer_name_lineedit.text()
        fields = self.fields_view.model().fields.to_json()
        versioning_mode = VersioningMode(
            self.versioning_combobox.currentData()
        )
        geometry_type = self.__current_geometry_type()
        assert geometry_type is not None
        if geometry_type != WkbType.NoGeometry and self.z_checkbox.isChecked():
            geometry_type = QgsWkbTypes.addZ(geometry_type)
        geometry_type_name = self.__ngw_geometry_type(geometry_type)

        feature_layer: Dict[str, Any] = dict(fields=fields)
        if versioning_mode != VersioningMode.AUTO:
            feature_layer["versioning"] = dict(
                enabled=versioning_mode == VersioningMode.ENABLED
            )

        vector_layer: Dict[str, Any] = dict(
            geometry_type=geometry_type_name,
            fields=[],
        )
        if geometry_type != WkbType.NoGeometry:
            vector_layer["srs"] = dict(id=3857)

        resource = dict(
            resource=dict(
                cls=NGWVectorLayer.type_id,
                parent=dict(id=parent_id),
                display_name=display_name,
            ),
            feature_layer=feature_layer,
            vector_layer=vector_layer,
        )
        ResourceCreator._add_metadata(
            resource,
            ResourceCreator.resource_created_by_metadata(),
        )
        return resource

    def __save_creation_settings(self) -> None:
        NgConnectSettings().add_vector_layer_after_creation = (
            self.add_to_project_checkbox.isChecked()
        )

    @property
    def resource(self) -> Optional[Dict[str, Any]]:
        return self.__result_resource

    @property
    def add_to_project(self) -> bool:
        return self.add_to_project_checkbox.isChecked()

    def enable_boolean_field_type(self):
        if self.__has_boolean_support:
            return

        self.__has_boolean_support = True
        self.field_type_combobox.addItem(
            NgwDataType.BOOLEAN.icon,
            NgwDataType.BOOLEAN.name,
            NgwDataType.BOOLEAN.qt_value,
        )

    def enable_json_field_type(self):
        if self.__has_json_support:
            return

        self.__has_json_support = True
        self.field_type_combobox.addItem(
            NgwDataType.JSON.icon,
            NgwDataType.JSON.name,
            NgwDataType.JSON.qt_value,
        )

    def enable_no_geometry_layer_type(self) -> None:
        if self.__has_no_geometry_support:
            return

        self.__has_no_geometry_support = True
        self.__add_geometry_type(WkbType.NoGeometry)

    def keyPressEvent(self, a0: Optional[QKeyEvent]) -> None:
        assert a0 is not None
        if a0.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            a0.accept()
            return
        super().keyPressEvent(a0)

    def __setup_ui(self) -> None:
        self.setupUi(self)
        QgsGui.enableAutoGeometryRestore(self)

        self.__setup_tabs()
        self.__setup_new_field_ui()
        self.__setup_fields_view()
        self.__setup_button_box()

    def __setup_tabs(self) -> None:
        # Init validation
        self.layer_name_lineedit.setText(
            generate_unique_name(
                self.tr("Vector Layer"), self.__siblings_names()
            )
        )
        self.layer_name_lineedit.textChanged.connect(self.__validate)
        self.geometry_combobox.currentIndexChanged.connect(self.__validate)
        self.geometry_combobox.currentIndexChanged.connect(
            self.__update_geometry_controls
        )

        # Init parent
        self.parent_combobox.setModel(self.__resources_model)
        self.parent_combobox.setRootModelIndex(
            self.__parent_resource_index.parent()
        )
        self.parent_combobox.setCurrentIndex(
            self.__parent_resource_index.row()
        )

        # Init warnings
        warning_icon = qgis_icon("mIconWarning.svg")
        size = int(max(24.0, self.layer_name_lineedit.minimumSize().height()))
        pixmap = warning_icon.pixmap(
            warning_icon.actualSize(QSize(size, size))
        )

        self.layer_name_warning_label.setPixmap(pixmap)
        self.layer_name_warning_label.hide()

        for geometry_type in self.SUPPORTED_WKB_TYPES:
            self.__add_geometry_type(geometry_type)

        # Set invalid geometry type for conscious choice
        self.geometry_combobox.setCurrentIndex(-1)
        self.__update_geometry_controls()

        versioning_tooltip = self.tr(
            "In auto mode, NextGIS Web decides whether to enable feature "
            "versioning."
        )
        self.versioning_label.setToolTip(versioning_tooltip)
        self.versioning_combobox.setToolTip(versioning_tooltip)
        self.versioning_combobox.addItem(
            self.tr("Auto"),
            VersioningMode.AUTO.value,
        )
        self.versioning_combobox.addItem(
            self.tr("Enabled"),
            VersioningMode.ENABLED.value,
        )
        self.versioning_combobox.addItem(
            self.tr("Disabled"),
            VersioningMode.DISABLED.value,
        )
        self.versioning_combobox.setCurrentIndex(0)

    def __setup_new_field_ui(self) -> None:
        # Init warning
        warning_icon = qgis_icon("mIconWarning.svg")
        size = int(
            max(24.0, self.field_keyname_lineedit.minimumSize().height())
        )
        pixmap = warning_icon.pixmap(
            warning_icon.actualSize(QSize(size, size))
        )
        self.field_keyname_warning_label.setPixmap(pixmap)
        self.field_keyname_warning_label.hide()

        # Init field name
        self.add_field_button.setEnabled(False)
        self.__display_name_last_value = ""
        self.field_display_name_lineedit.textChanged.connect(
            self.__on_display_name_changed
        )
        self.field_keyname_lineedit.textChanged.connect(
            self.__validate_new_field
        )
        self.field_keyname_lineedit.returnPressed.connect(self.__add_field)
        self.field_display_name_lineedit.returnPressed.connect(
            self.__add_field
        )

        display_name_tooltip = self.tr(
            "Display name that is used in the identification window instead "
            "of the keyname."
        )
        self.field_display_name_label.setToolTip(display_name_tooltip)
        self.field_display_name_lineedit.setToolTip(display_name_tooltip)

        keyname_tooltip = self.tr(
            "Technical name of the attribute, can be comprised only of plain "
            "latin symbols."
        )
        self.field_keyname_label.setToolTip(keyname_tooltip)
        self.field_keyname_lineedit.setToolTip(keyname_tooltip)

        self.field_type_label.setToolTip(self.__field_type_tooltip())
        self.field_type_combobox.setToolTip(self.__field_type_tooltip())
        self.field_type_combobox.currentIndexChanged.connect(
            self.__update_field_type_tooltip
        )

        self.required_checkbox.setToolTip(
            self.tr("The attribute must have a value.")
        )
        self.feature_table_checkbox.setToolTip(
            self.tr("The attribute is displayed in the identification window.")
        )
        self.text_search_checkbox.setToolTip(
            self.tr(
                "You can disable text search in the values of the attribute."
            )
        )
        self.label_attribute_checkbox.setToolTip(
            self.tr(
                "Value from this field is used as feature name for search "
                "results, identification and bookmarks."
            )
        )

        # Init field types
        for ngw_type in NgwDataType:
            if (
                ngw_type == NgwDataType.BOOLEAN
                and not self.__has_boolean_support
            ):
                continue

            if ngw_type == NgwDataType.JSON and not self.__has_json_support:
                continue

            self.field_type_combobox.addItem(
                ngw_type.icon, ngw_type.name, ngw_type.qt_value
            )
            item_index = self.field_type_combobox.count() - 1
            self.field_type_combobox.setItemData(
                item_index,
                self.__field_type_tooltip(ngw_type),
                Qt.ItemDataRole.ToolTipRole,
            )

        self.__update_field_type_tooltip()

        # Setup button
        self.add_field_button.setIcon(qgis_icon("mActionNewAttribute.svg"))
        self.add_field_button.setToolTip(self.tr("Add field to the list."))
        self.add_field_button.clicked.connect(self.__add_field)

    def __setup_fields_view(self):
        # Init icons
        self.remove_field_button.setIcon(
            qgis_icon("mActionDeleteAttribute.svg")
        )
        self.move_up_button.setIcon(qgis_icon("mActionArrowUp.svg"))
        self.move_down_button.setIcon(qgis_icon("mActionArrowDown.svg"))
        self.remove_field_button.setToolTip(
            self.tr("Remove selected field from the list.")
        )
        self.move_up_button.setToolTip(
            self.tr("Move selected field up in the list.")
        )
        self.move_down_button.setToolTip(
            self.tr("Move selected field down in the list.")
        )

        # Init buttons
        self.remove_field_button.clicked.connect(self.__remove_fields)
        self.move_up_button.clicked.connect(self.__move_field_up)
        self.move_down_button.clicked.connect(self.__move_field_down)

        # Init model
        model = NgwFieldsModel(None, self.fields_view)

        # Setup view
        self.fields_view.setModel(model)
        self.fields_view.horizontalHeader().setSectionResizeMode(
            NgwFieldsModel.Column.DISPLAY_NAME, QHeaderView.ResizeMode.Stretch
        )
        self.fields_view.horizontalHeader().setSectionResizeMode(
            NgwFieldsModel.Column.KEYNAME, QHeaderView.ResizeMode.Stretch
        )
        self.fields_view.setColumnWidth(NgwFieldsModel.Column.IS_LABEL, 20)
        self.fields_view.setColumnWidth(
            NgwFieldsModel.Column.IS_USED_FOR_SEARCH, 20
        )
        self.fields_view.setColumnWidth(NgwFieldsModel.Column.IS_REQUIRED, 20)
        self.fields_view.setColumnWidth(NgwFieldsModel.Column.IS_VISIBLE, 20)
        self.__header_proxy_style = HeaderWithCenteredIconProxyStyle()
        self.fields_view.horizontalHeader().setStyle(self.__header_proxy_style)
        self.fields_view.doubleClicked.connect(self.__on_double_clicked)

        model.rowsInserted.connect(self.__update_fields_view_buttons)
        model.rowsInserted.connect(self.__validate)
        model.rowsRemoved.connect(self.__update_fields_view_buttons)
        model.rowsRemoved.connect(self.__validate)
        model.rowsMoved.connect(self.__update_fields_view_buttons)
        self.fields_view.selectionModel().selectionChanged.connect(
            self.__update_fields_view_buttons
        )
        self.__update_fields_view_buttons()

        datatype_delegate = NgwDataTypeDelegate(self.fields_view)
        self.fields_view.setItemDelegateForColumn(
            NgwFieldsModel.Column.DATATYPE, datatype_delegate
        )

        checkbox_delegate = CheckBoxDelegate(self.fields_view)
        self.fields_view.setItemDelegateForColumn(
            NgwFieldsModel.Column.IS_REQUIRED, checkbox_delegate
        )
        self.fields_view.setItemDelegateForColumn(
            NgwFieldsModel.Column.IS_VISIBLE, checkbox_delegate
        )
        self.fields_view.setItemDelegateForColumn(
            NgwFieldsModel.Column.IS_USED_FOR_SEARCH, checkbox_delegate
        )
        self.fields_view.setItemDelegateForColumn(
            NgwFieldsModel.Column.IS_LABEL, checkbox_delegate
        )

    def __field_type_tooltip(
        self, ngw_type: Optional[NgwDataType] = None
    ) -> str:
        if ngw_type is None:
            return self.tr("Select attribute value type.")

        descriptions = {
            NgwDataType.INTEGER: self.tr(
                "Numbers between -2147483647 and 2147483647, no decimals."
            ),
            NgwDataType.BIGINT: self.tr(
                "Long numbers without decimals, between -9223372036854775807 "
                "and 9223372036854775807."
            ),
            NgwDataType.REAL: self.tr("Floating-point numbers, e.g. 44.4444."),
            NgwDataType.STRING: self.tr("A text of any length."),
            NgwDataType.JSON: self.tr("Structured JSON data."),
            NgwDataType.DATE: self.tr("Date."),
            NgwDataType.TIME: self.tr("Time."),
            NgwDataType.DATETIME: self.tr("Date and time."),
            NgwDataType.BOOLEAN: self.tr(
                'Logical field, possible values are "TRUE" and "FALSE".'
            ),
        }
        return descriptions.get(
            ngw_type, self.tr("Select attribute value type.")
        )

    def __update_field_type_tooltip(self) -> None:
        ngw_type = self.__current_field_type()
        if ngw_type is None:
            self.field_type_combobox.setToolTip(self.__field_type_tooltip())
            return

        self.field_type_combobox.setToolTip(
            self.__field_type_tooltip(ngw_type)
        )

    def __current_field_type(self) -> Optional[NgwDataType]:
        current_data = self.field_type_combobox.currentData()
        if current_data in (None, ""):
            return None

        try:
            return NgwDataType.from_qt_value(current_data)
        except (TypeError, ValueError):
            return None

    def __setup_button_box(
        self,
    ):
        self.add_to_project_checkbox.setChecked(
            NgConnectSettings().add_vector_layer_after_creation
        )

        original_add_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Save
        )
        assert original_add_button is not None

        add_button = LoadingPushButton(
            icon=original_add_button.icon(),
            parent=self.button_box,
        )
        add_button.setText(self.tr("Create"))
        add_button.setEnabled(False)
        add_button.setAutoDefault(original_add_button.autoDefault())
        add_button.setDefault(original_add_button.isDefault())
        self.button_box.removeButton(original_add_button)
        original_add_button.hide()
        original_add_button.deleteLater()
        self.button_box.addButton(
            add_button,
            QDialogButtonBox.ButtonRole.AcceptRole,
        )
        self.__create_button = add_button

        add_button.clicked.connect(self.__create_clicked)
        self.validity_changed.connect(add_button.setEnabled)

        close_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        close_button.clicked.connect(self.reject)

    def __create_clicked(self) -> None:
        if self.__is_creating:
            return

        if self.__create_resource is None:
            self.accept()
            return

        self.__result_resource = self.__build_resource()
        self.__save_creation_settings()
        assert self.__result_resource is not None

        self.__start_creation()
        response = self.__create_resource(self.__result_resource)
        if response is None:
            self.__stop_creation()
            return

        response.done.connect(self.__creation_done)
        response.failed.connect(self.__creation_failed)
        response.finished.connect(self.__creation_finished)

    def __start_creation(self) -> None:
        self.__is_creating = True
        assert self.__create_button is not None
        self.__create_button.start()
        close_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if close_button is not None:
            close_button.setEnabled(False)

    def __stop_creation(self) -> None:
        self.__is_creating = False
        assert self.__create_button is not None
        self.__create_button.stop()
        close_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Cancel
        )
        if close_button is not None:
            close_button.setEnabled(True)

    def __creation_done(self, _: QModelIndex) -> None:
        self.__stop_creation()
        super().accept()

    def __creation_failed(self, _: object) -> None:
        self.__stop_creation()

    def __creation_finished(self) -> None:
        if self.__is_creating:
            self.__stop_creation()

    def __validate_new_field(self):
        keyname = self.field_keyname_lineedit.text()
        display_name = self.field_display_name_lineedit.text()

        need_tooltip = False
        tooltip = ""

        if self.fields_view.model().has_field(keyname):
            need_tooltip = True
            tooltip = self.tr("Keyname already exists")

        elif keyname in ("geom",):
            need_tooltip = True
            tooltip = self.tr("Keyname reserved by NextGIS Web")

        self.field_keyname_warning_label.setVisible(need_tooltip)
        self.field_keyname_warning_label.setToolTip(tooltip)

        is_valid = (
            len(display_name) > 0 and len(keyname) > 0 and not need_tooltip
        )

        self.add_field_button.setEnabled(is_valid)

    def __update_fields_view_buttons(self):
        selection = self.fields_view.selectionModel()
        selected_rows = selection.selectedRows()

        remove_enabled = False
        move_up_enabled = False
        move_down_enabled = False

        if len(selected_rows) == 1:
            remove_enabled = True
            selected_row = selected_rows[0].row()
            first_row = 0
            move_up_enabled = selected_row > first_row
            last_row = self.fields_view.model().rowCount() - 1
            move_down_enabled = selected_row < last_row
        elif len(selected_rows) > 1:
            remove_enabled = True

        self.remove_field_button.setEnabled(remove_enabled)
        self.move_up_button.setEnabled(move_up_enabled)
        self.move_down_button.setEnabled(move_down_enabled)

    def __validate(self):
        geometry_id_valid = self.geometry_combobox.currentIndex() >= 0
        layer_name = self.layer_name_lineedit.text()
        layer_name_is_valid = len(layer_name) > 0
        layer_name_is_unique = layer_name not in self.__siblings_names()

        self.layer_name_warning_label.setVisible(not layer_name_is_unique)

        self.validity_changed.emit(
            geometry_id_valid and layer_name_is_valid and layer_name_is_unique
        )

    def __add_geometry_type(self, geometry_type: WkbType) -> None:
        self.geometry_combobox.addItem(
            wkb_type_icon(geometry_type),
            QgsWkbTypes.translatedDisplayString(geometry_type),
            int(geometry_type),
        )

    def __update_geometry_controls(self) -> None:
        geometry_type = self.__current_geometry_type()
        has_geometry = (
            geometry_type is None or geometry_type != WkbType.NoGeometry
        )
        self.z_checkbox.setEnabled(has_geometry)
        if not has_geometry:
            self.z_checkbox.setChecked(False)

    def __current_geometry_type(self) -> Optional[WkbType]:
        geometry_type = self.geometry_combobox.currentData()
        if geometry_type is None:
            return None

        return WkbType(geometry_type)

    def __ngw_geometry_type(self, geometry_type: WkbType) -> str:
        if geometry_type == WkbType.NoGeometry:
            return self.NO_GEOMETRY_TYPE

        return QgsWkbTypes.displayString(geometry_type).upper()

    def __add_field(self):
        if not self.add_field_button.isEnabled():
            return

        cast(NgwFieldsModel, self.fields_view.model()).create_field(
            self.field_display_name_lineedit.text(),
            self.field_keyname_lineedit.text(),
            NgwDataType.from_qt_value(self.field_type_combobox.currentData()),
            is_label=self.label_attribute_checkbox.isChecked(),
            is_required=self.required_checkbox.isChecked(),
            is_visible=self.feature_table_checkbox.isChecked(),
            is_used_for_search=self.text_search_checkbox.isChecked(),
        )
        self.field_display_name_lineedit.clear()
        self.field_keyname_lineedit.clear()
        self.field_display_name_lineedit.setFocus()
        self.label_attribute_checkbox.setChecked(False)
        self.required_checkbox.setChecked(False)

        for column in (
            NgwFieldsModel.Column.IS_REQUIRED,
            NgwFieldsModel.Column.IS_VISIBLE,
            NgwFieldsModel.Column.IS_USED_FOR_SEARCH,
            NgwFieldsModel.Column.IS_LABEL,
        ):
            self.fields_view.openPersistentEditor(
                self.fields_view.model().index(
                    self.fields_view.model().rowCount() - 1, column
                )
            )

    def __remove_fields(self):
        selection = self.fields_view.selectionModel()
        selected_rows = [index.row() for index in selection.selectedRows()]
        selected_rows.sort(reverse=True)

        for row in selected_rows:
            self.fields_view.model().removeRow(row)

        self.__validate_new_field()

    @pyqtSlot()
    def __move_field_up(self):
        model = self.fields_view.model()
        if model.rowCount() == 0:
            return

        selection = self.fields_view.selectionModel()
        selected_rows = selection.selectedRows()
        first_row = 0
        if len(selected_rows) != 1 or selected_rows[0].row() == first_row:
            return

        row = selected_rows[0].row()
        model.moveRow(QModelIndex(), row, QModelIndex(), row - 1)

    @pyqtSlot()
    def __move_field_down(self):
        model = self.fields_view.model()
        if model.rowCount() == 0:
            return

        selection = self.fields_view.selectionModel()
        selected_rows = selection.selectedRows()

        last_row = model.rowCount() - 1
        if len(selected_rows) != 1 or selected_rows[0].row() == last_row:
            return

        row = selected_rows[0].row()
        model.moveRow(QModelIndex(), row, QModelIndex(), row + 1)

    @pyqtSlot(str)
    def __on_display_name_changed(self, new_value: str) -> None:
        keyname = self.field_keyname_lineedit.text()
        keyname_from_last_value = self.__display_name_to_keyname(
            self.__display_name_last_value
        )
        if keyname_from_last_value == keyname:
            self.field_keyname_lineedit.setText(
                self.__display_name_to_keyname(new_value)
            )
        self.__display_name_last_value = new_value
        self.__validate_new_field()

    @pyqtSlot(QModelIndex)
    def __on_double_clicked(self, index: QModelIndex) -> None:
        if index.column() not in (
            NgwFieldsModel.Column.IS_VISIBLE,
            NgwFieldsModel.Column.IS_USED_FOR_SEARCH,
            NgwFieldsModel.Column.IS_LABEL,
        ):
            return

        model = self.fields_view.model()
        value = model.data(index, Qt.ItemDataRole.EditRole)
        model.setData(index, not value, Qt.ItemDataRole.EditRole)

    def __display_name_to_keyname(self, display_name: str) -> str:
        return "".join(
            char if char.isalnum() or char == "_" else "_"
            for char in display_name.lower()
        )

    def __siblings_names(self) -> List[str]:
        return [
            self.__resources_model.data(
                self.__resources_model.index(
                    row, 0, self.__parent_resource_index
                )
            )
            for row in range(
                self.__resources_model.rowCount(self.__parent_resource_index)
            )
        ]
