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

from typing import Optional

from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, Qt
from qgis.PyQt.QtWidgets import (
    QComboBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)

from nextgis_connect.legacy.ngw.resources.ngw_data_type import NgwDataType
from nextgis_connect.legacy.ngw.resources.ngw_fields_model import (
    NgwFieldsModel,
)


class NgwDataTypeDelegate(QStyledItemDelegate):
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        if index.column() != NgwFieldsModel.Column.DATATYPE:
            return super().createEditor(parent, option, index)

        editor = QComboBox(parent)
        for datatype in NgwDataType:
            editor.addItem(datatype.icon, datatype.name, datatype.qt_value)
        return editor

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        if index.column() != NgwFieldsModel.Column.DATATYPE:
            super().setEditorData(editor, index)

        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        found_index = editor.findData(value)
        editor.setCurrentIndex(found_index)

    def setModelData(
        self,
        editor: QComboBox,
        model: Optional[QAbstractItemModel],
        index: QModelIndex,
    ) -> None:
        if index.column() != NgwFieldsModel.Column.DATATYPE:
            super().setModelData(editor, model, index)

        model.setData(index, editor.currentData(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        editor.setGeometry(option.rect)
