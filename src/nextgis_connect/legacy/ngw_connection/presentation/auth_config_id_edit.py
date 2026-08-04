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

import re
from typing import Optional

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLineEdit,
    QSizePolicy,
    QToolButton,
    QWidget,
)

from nextgis_connect.ui_kit.icons import qgis_checkable_icon


class AuthConfigIdEdit(QWidget):
    """
    Widget for editing a QGIS authentication configuration ID.
    """

    AUTH_CONFIG_ID_LENGTH = 7

    validityChanged = pyqtSignal(bool)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        authcfg: str = "",
        allow_empty: bool = True,
    ) -> None:
        super().__init__(parent)
        self.__original_auth_config_id = authcfg
        self.__allow_empty = allow_empty
        self.__is_valid = False

        self.__setup_ui()
        self.auth_config_line_edit.setReadOnly(True)
        self.auth_config_line_edit.setText(authcfg)
        self.__sync_lock_button_height()

        lock_icon = qgis_checkable_icon("locked.svg", "unlocked.svg")
        self.lock_button.setIcon(lock_icon)

        self.lock_button.toggled.connect(self.__on_lock_toggled)
        self.auth_config_line_edit.textChanged.connect(
            self.__on_auth_config_id_changed
        )
        self.validityChanged.connect(self.update_validity_style)

        self.update_validity_style(self.validate())

    def config_id(self) -> str:
        if not self.validate():
            return ""
        return self.auth_config_line_edit.text()

    def auth_config_id_text(self) -> str:
        return self.auth_config_line_edit.text()

    def allows_empty_id(self) -> bool:
        return self.__allow_empty

    def validate(self) -> bool:
        auth_config_id = self.auth_config_line_edit.text()
        is_valid = self.__is_unchanged_existing_id(auth_config_id) or (
            self.__allow_empty and len(auth_config_id) == 0
        )

        auth_manager = QgsApplication.authManager()
        can_check_uniqueness = (
            not auth_manager.isDisabled()
            and not is_valid
            and len(auth_config_id) == self.AUTH_CONFIG_ID_LENGTH
            and self.is_alphanumeric(auth_config_id)
        )
        if can_check_uniqueness:
            is_valid = auth_manager.configIdUnique(auth_config_id)

        if self.__is_valid != is_valid:
            self.__is_valid = is_valid
            self.validityChanged.emit(is_valid)

        return is_valid

    def set_auth_config_id(self, auth_config_id: str) -> None:
        if len(self.__original_auth_config_id) == 0:
            self.__original_auth_config_id = auth_config_id
        self.auth_config_line_edit.setText(auth_config_id)
        self.validate()

    def reset_auth_config_id(
        self,
        auth_config_id: str = "",
        *,
        allow_empty: Optional[bool] = None,
    ) -> None:
        self.__original_auth_config_id = auth_config_id
        if allow_empty is not None:
            self.__allow_empty = allow_empty

        self.lock_button.setChecked(False)
        self.auth_config_line_edit.setReadOnly(True)
        self.auth_config_line_edit.setText(auth_config_id)
        self.validate()

    def set_empty_id_allowed(self, allowed: bool) -> None:
        self.__allow_empty = allowed
        self.validate()

    def clear(self) -> None:
        self.auth_config_line_edit.setText(self.__original_auth_config_id)
        self.update_validity_style(True)

    def update_validity_style(self, is_valid: bool) -> None:
        red = QColor(200, 0, 0).name()
        yellow = QColor(255, 255, 125).name()

        stylesheet = "QLineEdit{"
        if not is_valid:
            stylesheet += f"color: {red};"
        if self.lock_button.isChecked():
            stylesheet += f"background-color: {yellow}; color: black;"
        stylesheet += "}"

        self.auth_config_line_edit.setStyleSheet(stylesheet)

    @staticmethod
    def is_alphanumeric(auth_config_id: str) -> bool:
        return re.fullmatch(r"[a-zA-Z0-9]{7}", auth_config_id) is not None

    def __setup_ui(self) -> None:
        self.setSizePolicy(
            QSizePolicy.Policy.Maximum,
            QSizePolicy.Policy.Maximum,
        )
        self.setMaximumWidth(120)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.auth_config_line_edit = QLineEdit(self)
        self.auth_config_line_edit.setMinimumWidth(80)
        self.auth_config_line_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.auth_config_line_edit.setPlaceholderText(self.tr("Generated"))
        layout.addWidget(self.auth_config_line_edit)

        self.lock_button = QToolButton(self)
        self.lock_button.setToolTip(
            self.tr(
                "Unlock to edit the ID\n"
                "7-character alphanumeric only\n"
                "Editing may break existing references."
            )
        )
        self.lock_button.setText("...")
        self.lock_button.setCheckable(True)
        layout.addWidget(self.lock_button)

    def __sync_lock_button_height(self) -> None:
        height = self.auth_config_line_edit.sizeHint().height()
        self.lock_button.setFixedSize(height, height)

    def __is_unchanged_existing_id(self, auth_config_id: str) -> bool:
        return (
            auth_config_id == self.__original_auth_config_id
            and len(auth_config_id) == self.AUTH_CONFIG_ID_LENGTH
        )

    def __on_lock_toggled(self, checked: bool) -> None:
        self.auth_config_line_edit.setReadOnly(not checked)
        if checked:
            self.auth_config_line_edit.setFocus()
        self.update_validity_style(self.validate())

    def __on_auth_config_id_changed(self, _: str) -> None:
        self.validate()
