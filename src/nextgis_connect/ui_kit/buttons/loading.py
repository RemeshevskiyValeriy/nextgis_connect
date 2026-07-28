# NextGIS Toolbox
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

from qgis.PyQt.QtCore import (
    QCoreApplication,
    QEvent,
    QRect,
    QSize,
    Qt,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QEnterEvent, QIcon, QMouseEvent
from qgis.PyQt.QtWidgets import QPushButton, QToolButton, QWidget

from nextgis_connect.ui_kit.widgets.loading_indicator import (
    LoadingIndicatorIconAnimator,
)


class LoadingButtonMixin:
    """Provide loading-state behavior for button widgets.

    Manage animated loading icons, optional cancel icons, and cancel
    request signaling for concrete Qt button classes.
    """

    def _initialize_loading_button(
        self,
        icon: Optional[QIcon] = None,
        cancel_icon: Optional[QIcon] = None,
        animation_path: Optional[str] = None,
    ) -> None:
        del animation_path

        self._default_icon = QIcon() if icon is None else QIcon(icon)
        self._set_icon(self._default_icon)
        self._cancel_icon = (
            QIcon() if cancel_icon is None else QIcon(cancel_icon)
        )
        self._default_tooltip = self._tool_tip()
        self._enabled_before_loading = self._is_enabled()
        self._is_hovered = False
        self._is_loading = False
        self._loading_icon = LoadingIndicatorIconAnimator(
            self._icon_size(),
            parent=self,
        )
        self._loading_icon.frame_changed.connect(self._update_loading_icon)

    def is_loading(self) -> bool:
        """Return whether loading is active.

        :return: ``True`` when the button is in loading state.
        """
        return self._is_loading

    def cancel_icon(self) -> QIcon:
        """Return the cancel icon.

        :return: Copy of the cancel icon.
        """
        return QIcon(self._cancel_icon)

    def set_cancel_icon(self, icon: QIcon) -> None:
        """Set the cancel icon.

        :param icon: Cancel icon to show on hover during loading.
        """
        self._cancel_icon = QIcon(icon)

    def _start_loading(self) -> None:
        if self._is_loading:
            return

        self._default_icon = self._icon()
        self._default_tooltip = self._tool_tip()
        self._enabled_before_loading = self._is_enabled()
        self._is_loading = True

        if self._cancel_icon.isNull():
            self._set_enabled(False)
        else:
            self._set_tool_tip(
                QCoreApplication.translate("LoadingButton", "Cancel")
            )

        icon_size = self._icon_size()
        if not icon_size.isValid():
            icon_size = QSize(16, 16)

        self._loading_icon.set_size(icon_size)
        self._loading_icon.start()
        self._update_loading_icon()

    def _stop_loading(self) -> None:
        if self._loading_icon.is_running():
            self._loading_icon.stop()

        self._is_loading = False
        self._set_icon(self._default_icon)
        self._set_tool_tip(self._default_tooltip)
        if self._cancel_icon.isNull():
            self._set_enabled(self._enabled_before_loading)

    def _handle_enter_event(self) -> None:
        self._is_hovered = True
        if self._is_loading and not self._cancel_icon.isNull():
            self._set_icon(self._cancel_icon)

    def _handle_leave_event(self) -> None:
        self._is_hovered = False
        if self._is_loading:
            self._update_loading_icon()

    def _handle_mouse_release_event(
        self,
        event: Optional[QMouseEvent],
    ) -> bool:
        if event is None:
            return False

        if not self._is_loading:
            return False

        if event.button() != Qt.MouseButton.LeftButton:
            return False

        if self._cancel_icon.isNull():
            return False

        event.accept()

        if not self._is_enabled() or not self._rect().contains(event.pos()):
            return True

        self._cancel_requested_signal().emit()
        return True

    def _handle_icon_size_change(self, size: QSize) -> None:
        if size.isValid():
            self._loading_icon.set_size(size)

    def _update_loading_icon(self) -> None:
        if self._is_hovered and not self._cancel_icon.isNull():
            self._set_icon(self._cancel_icon)
            return

        self._set_icon(
            self._loading_icon.current_icon(
                palette=self.palette(),
                device_pixel_ratio=self.devicePixelRatioF(),
            )
        )

    def _set_icon(self, icon: QIcon) -> None:
        self.setIcon(icon)

    def _icon(self) -> QIcon:
        return self.icon()

    def _tool_tip(self) -> str:
        return self.toolTip()

    def _set_tool_tip(self, tooltip: str) -> None:
        self.setToolTip(tooltip)

    def _icon_size(self) -> QSize:
        return self.iconSize()

    def _is_enabled(self) -> bool:
        return self.isEnabled()

    def _set_enabled(self, is_enabled: bool) -> None:
        self.setEnabled(is_enabled)

    def _rect(self) -> QRect:
        return self.rect()

    def _cancel_requested_signal(self) -> pyqtSignal:
        return self.cancelRequested


class LoadingPushButton(LoadingButtonMixin, QPushButton):
    """Show a push button with loading feedback.

    Switch the button icon to an animated loading indicator and emit a
    cancel signal when a cancel icon is available and clicked.
    """

    cancel_requested = pyqtSignal()

    def __init__(
        self,
        icon: Optional[QIcon] = None,
        cancel_icon: Optional[QIcon] = None,
        animation_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the loading push button.

        :param icon: Default button icon.
        :param cancel_icon: Icon used for cancel requests.
        :param animation_path: Loading animation asset path.
        :param parent: Parent widget.
        """
        super().__init__(parent)
        self._initialize_loading_button(
            icon=icon,
            cancel_icon=cancel_icon,
            animation_path=animation_path,
        )

    def start(self) -> None:
        """Start loading feedback."""
        self._start_loading()

    def stop(self) -> None:
        """Stop loading feedback."""
        self._stop_loading()

    def enterEvent(self, event: Optional[QEnterEvent]) -> None:
        """Handle pointer enter events.

        :param event: Qt enter event.
        """
        self._handle_enter_event()
        super().enterEvent(event)

    def leaveEvent(self, a0: Optional[QEvent]) -> None:
        """Handle pointer leave events.

        :param a0: Qt leave event.
        """
        self._handle_leave_event()
        super().leaveEvent(a0)

    def mouseReleaseEvent(self, e: Optional[QMouseEvent]) -> None:
        """Handle mouse release events.

        :param e: Qt mouse event.
        """
        if self._handle_mouse_release_event(e):
            return

        super().mouseReleaseEvent(e)

    def setIconSize(self, size: QSize) -> None:
        """Set the icon size.

        :param size: New icon size.
        """
        super().setIconSize(size)
        self._handle_icon_size_change(size)


class LoadingToolButton(LoadingButtonMixin, QToolButton):
    """Show a tool button with loading feedback.

    Switch the button icon to an animated loading indicator and emit a
    cancel signal when a cancel icon is available and clicked.
    """

    cancel_requested = pyqtSignal()

    def __init__(
        self,
        icon: Optional[QIcon] = None,
        cancel_icon: Optional[QIcon] = None,
        animation_path: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """Initialize the loading tool button.

        :param icon: Default button icon.
        :param cancel_icon: Icon used for cancel requests.
        :param animation_path: Loading animation asset path.
        :param parent: Parent widget.
        """
        super().__init__(parent)
        self._initialize_loading_button(
            icon=icon,
            cancel_icon=cancel_icon,
            animation_path=animation_path,
        )

    def start(self) -> None:
        """Start loading feedback."""
        self._start_loading()

    def stop(self) -> None:
        """Stop loading feedback."""
        self._stop_loading()

    def enterEvent(self, a0: Optional[QEnterEvent]) -> None:
        """Handle pointer enter events.

        :param a0: Qt enter event.
        """
        self._handle_enter_event()
        super().enterEvent(a0)

    def leaveEvent(self, a0: Optional[QEvent]) -> None:
        """Handle pointer leave events.

        :param a0: Qt leave event.
        """
        self._handle_leave_event()
        super().leaveEvent(a0)

    def mouseReleaseEvent(self, a0: Optional[QMouseEvent]) -> None:
        """Handle mouse release events.

        :param a0: Qt mouse event.
        """
        if self._handle_mouse_release_event(a0):
            return

        super().mouseReleaseEvent(a0)

    def setIconSize(self, size: QSize) -> None:
        """Set the icon size.

        :param size: New icon size.
        """
        super().setIconSize(size)
        self._handle_icon_size_change(size)
