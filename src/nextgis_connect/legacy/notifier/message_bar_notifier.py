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
import uuid
from typing import TYPE_CHECKING, List, Optional

import qgis.utils
from qgis.core import Qgis
from qgis.PyQt.QtCore import QObject, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import QMessageBox, QPushButton, QWidget

from nextgis_connect.legacy.ngw_connection import NgwConnectionsManager
from nextgis_connect.legacy.ngw_connection.presentation.diagnostics import (
    NgwConnectionDiagnosticsDialog,
)
from nextgis_connect.legacy.notifier.notifier_interface import (
    NotifierInterface,
)
from nextgis_connect.platform.logging import logger, open_plugin_logs
from nextgis_connect.platform.qgis.errors import (
    ErrorCode,
    NgConnectError,
    NgConnectWarning,
)
from nextgis_connect.platform.qgis.utils import nextgis_domain, utm_tags
from nextgis_connect.shared.constants import PLUGIN_NAME
from nextgis_connect.ui_kit.icons import plugin_icon

if TYPE_CHECKING:
    from qgis.gui import QgisInterface


def _iface() -> "QgisInterface":
    iface = qgis.utils.iface
    assert iface is not None
    return iface


def let_us_know() -> None:
    """Open the issue tracker URL in the default web browser."""
    utm = utm_tags("error")
    QDesktopServices.openUrl(QUrl(f"{nextgis_domain()}/bugreport/?{utm}"))


def upgrade_plan():
    """Open the upgrade plan URL in the default web browser."""
    utm = utm_tags("quota")
    QDesktopServices.openUrl(QUrl(f"{nextgis_domain()}/pricing-base/?{utm}"))


def run_connection_diagnostics() -> None:
    """Open diagnostics for the current Web GIS connection."""
    iface = _iface()
    connection = NgwConnectionsManager().current_connection
    if connection is None:
        iface.showOptionsDialog(iface.mainWindow(), "NextGIS Connect")
        return

    dialog = NgwConnectionDiagnosticsDialog(connection, iface.mainWindow())
    dialog.exec()


class MessageBarNotifier(NotifierInterface):
    """Notifier implementation for displaying messages and exceptions in QGIS.

    Provides methods to show messages and exceptions using QGIS message bar.
    """

    def __init__(self, parent: Optional[QObject]) -> None:
        """Initialize MessageBarNotifier with an optional parent QObject.

        :param parent: The parent QObject for this notifier.
        """
        super().__init__(parent)

    def __del__(self) -> None:
        """Dismiss all messages on object deletion."""
        self.dismiss_all()

    def display_message(
        self,
        message: str,
        *,
        level: Qgis.MessageLevel = Qgis.MessageLevel.Info,
        widgets: Optional[List[QWidget]] = None,
        **kwargs,
    ) -> str:
        """Display a message to the user via the QGIS message bar.

        :param message: The message to display.
        :param level: The message level as Qgis.MessageLevel.
        :param widgets: Custom widgets for message.
        :return: An identifier for the displayed message.
        """
        custom_widgets = widgets if widgets else []

        iface = _iface()
        message_bar = iface.messageBar()
        widget = message_bar.createMessage(PLUGIN_NAME, message)

        for custom_widget in custom_widgets:
            custom_widget.setParent(widget)
            widget.layout().addWidget(custom_widget)

        item = message_bar.pushWidget(widget, level, **kwargs)
        item.setObjectName("NgConnectMessageBarItem")
        message_id = str(uuid.uuid4())
        item.setProperty("NgConnectMessageId", message_id)

        logger.log(level, message)

        return message_id

    def display_exception(self, error: Exception) -> str:
        """Display an exception as an error message to the user.

        :param error: The exception to display.
        :return: An identifier for the displayed message.
        """
        if not isinstance(error, (NgConnectError, NgConnectWarning)):
            old_error = error
            error = (
                NgConnectError()
                if not isinstance(error, Warning)
                else NgConnectWarning()
            )
            error.__cause__ = old_error
            del old_error

        message = error.user_message.rstrip(".") + "."

        iface = _iface()
        message_bar = iface.messageBar()
        widget = message_bar.createMessage(PLUGIN_NAME, message)

        if not isinstance(error, Warning):
            self._add_error_buttons(error, widget)

        level = (
            Qgis.MessageLevel.Critical
            if not isinstance(error, NgConnectWarning)
            else Qgis.MessageLevel.Warning
        )

        item = message_bar.pushWidget(widget, level)
        item.setObjectName("NgConnectMessageBarItem")
        item.setProperty("NgConnectMessageId", error.error_id)

        if level == Qgis.MessageLevel.Critical:
            logger.exception(error.log_message, exc_info=error)
        else:
            logger.warning(error.user_message)

        return error.error_id

    def dismiss_message(self, message_id: str) -> None:
        """Dismiss a specific message by its identifier.

        :param message_id: The identifier of the message to dismiss.
        """
        iface = _iface()
        for notification in iface.messageBar().items():
            if (
                notification.objectName() != "NgConnectMessageBarItem"
                or notification.property("NgConnectMessageId") != message_id
            ):
                continue
            iface.messageBar().popWidget(notification)

    def dismiss_all(self) -> None:
        """Dismiss all currently displayed messages."""
        iface = _iface()
        for notification in iface.messageBar().items():
            if notification.objectName() != "NgConnectMessageBarItem":
                continue
            iface.messageBar().popWidget(notification)

    def _add_error_buttons(
        self, error: NgConnectError, widget: QWidget
    ) -> None:
        def show_details() -> None:
            user_message = error.user_message.rstrip(".")
            user_message = re.sub(
                r"</?(i|b)\b[^>]*?>", "", user_message, flags=re.IGNORECASE
            )
            iface = _iface()
            QMessageBox.information(
                iface.mainWindow(), user_message, error.detail or ""
            )

        if error.try_again is not None:

            def try_again() -> None:
                error.try_again()
                _iface().messageBar().popWidget(widget)

            button = QPushButton(self.tr("Try again"))
            button.pressed.connect(try_again)
            widget.layout().addWidget(button)

        for action_name, action_callback in error.actions:
            button = QPushButton(action_name)
            button.pressed.connect(action_callback)
            widget.layout().addWidget(button)

        if error.code == ErrorCode.QuotaExceeded:
            button = QPushButton(self.tr("Upgrade your plan"))
            button.setIcon(plugin_icon("status/upgrade.svg"))
            button.pressed.connect(upgrade_plan)
            widget.layout().addWidget(button)

        elif error.is_network_problem or error.code.is_connection_error:
            button = QPushButton(self.tr("Run diagnostics"))
            button.pressed.connect(run_connection_diagnostics)
            widget.layout().addWidget(button)

        if error.detail is not None:
            button = QPushButton(self.tr("Details"))
            button.pressed.connect(show_details)
            widget.layout().addWidget(button)
        elif error.need_logs:
            button = QPushButton(self.tr("Open logs"))
            button.pressed.connect(open_plugin_logs)
            widget.layout().addWidget(button)

        if type(error) is NgConnectError:
            button = QPushButton(self.tr("Let us know"))
            button.pressed.connect(let_us_know)
            widget.layout().addWidget(button)
