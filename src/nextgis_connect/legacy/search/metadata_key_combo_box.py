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

from qgis.PyQt.QtCore import pyqtSignal, pyqtSlot
from qgis.PyQt.QtWidgets import QComboBox, QWidget

from nextgis_connect.legacy.search.search_settings import SearchSettings


class MetadataKeyComboBox(QComboBox):
    """
    A QComboBox subclass for selecting metadata keys with an editable line edit.
    """

    reset_requested = pyqtSignal()
    focus_value = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """
        Initializes the MetadataKeyComboBox.

        :param parent: The parent widget. Defaults to None.
        :type parent: Optional[QWidget]
        """
        super().__init__(parent)
        self.setEditable(True)
        self.lineEdit().setPlaceholderText(self.tr("Metadata key…"))
        self.lineEdit().textEdited.connect(self.__reset_if_empty)
        self.lineEdit().returnPressed.connect(self.focus_value)

        self.update_values()

    @pyqtSlot()
    def update_values(self) -> None:
        """
        Updates the available metadata keys in the combo box.

        This method clears the current items, retrieves metadata keys
        from SearchSettings, and repopulates the combo box while maintaining
        the user's current text input.
        """
        backup_text = self.lineEdit().text()

        self.clear()
        settings = SearchSettings()
        self.addItems(settings.metadata_keys)

        self.lineEdit().setText(backup_text)

    @pyqtSlot(str)
    def __reset_if_empty(self, search_string: str) -> None:
        if len(search_string) != 0:
            return

        self.reset_requested.emit()
