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
    QCheckBox,
    QComboBox,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QWidget,
)


class CheckBoxDelegate(QStyledItemDelegate):
    """Edit boolean item data with a centered checkbox.

    Create checkbox editors for item views and write their checked state
    back to the model edit role.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the checkbox delegate.

        :param parent: Parent widget.
        """
        super().__init__(parent)

    def createEditor(
        self, parent: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> QWidget:
        """Create a checkbox editor.

        :param parent: Parent editor widget.
        :param option: Style option for the edited item.
        :param index: Model index being edited.
        :return: Checkbox editor widget.
        """
        checkbox = QCheckBox(parent)
        checkbox.stateChanged.connect(lambda: self.commitData.emit(checkbox))
        return checkbox

    def setEditorData(self, editor: QComboBox, index: QModelIndex):
        """Populate the editor from model data.

        :param editor: Checkbox editor widget.
        :param index: Model index being edited.
        """
        value = index.model().data(index, Qt.ItemDataRole.EditRole)
        editor.setChecked(bool(value))

    def setModelData(
        self,
        editor: QComboBox,
        model: Optional[QAbstractItemModel],
        index: QModelIndex,
    ) -> None:
        """Write the editor value to the model.

        :param editor: Checkbox editor widget.
        :param model: Model to update.
        :param index: Model index being edited.
        """
        model.setData(index, editor.isChecked(), Qt.ItemDataRole.EditRole)

    def updateEditorGeometry(
        self, editor: QWidget, option: QStyleOptionViewItem, index: QModelIndex
    ) -> None:
        """Center the editor inside the item rectangle.

        :param editor: Editor widget to position.
        :param option: Style option for the edited item.
        :param index: Model index being edited.
        """
        rect = option.rect
        editor.setGeometry(
            rect.x() + (rect.width() - editor.sizeHint().width()) // 2,
            rect.y() + (rect.height() - editor.sizeHint().height()) // 2,
            editor.sizeHint().width(),
            editor.sizeHint().height(),
        )
