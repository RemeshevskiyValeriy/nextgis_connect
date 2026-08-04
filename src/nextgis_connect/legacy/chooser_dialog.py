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

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)


class ChooserDialog(QDialog):
    """Show a simple multi-selection dialog.

    Present a list of text options and store the selected values after
    the dialog is accepted.

    :ivar options: Text options shown to the caller.
    :ivar seleced_options: Text options selected by the user.
    """

    def __init__(self, options):
        """Initialize the chooser dialog.

        :param options: Text options to display.
        """
        super().__init__()
        self.options = options

        self.setLayout(QVBoxLayout())

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list.setSelectionBehavior(
            QListWidget.SelectionBehavior.SelectItems
        )
        self.layout().addWidget(self.list)

        for option in options:
            item = QListWidgetItem(option)
            self.list.addItem(item)

        self.list.setCurrentRow(0)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok,
            Qt.Orientation.Horizontal,
            self,
        )
        ok_button = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
        assert ok_button is not None
        ok_button.clicked.connect(self.accept)
        self.layout().addWidget(self.btn_box)

        self.seleced_options = []

    def accept(self):
        """Accept the dialog and store selected options."""
        self.seleced_options = [
            item.text() for item in self.list.selectedItems()
        ]
        super().accept()
