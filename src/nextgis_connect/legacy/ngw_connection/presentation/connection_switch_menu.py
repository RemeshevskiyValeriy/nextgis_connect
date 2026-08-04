from typing import List, Optional, Tuple, cast

from qgis.PyQt.QtCore import Qt, pyqtSignal, pyqtSlot
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QMenu,
    QToolButton,
    QWidget,
)

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.legacy.ngw_connection.presentation.connection_edit_dialog import (
    LoginChoice,
    LoginChoiceKind,
    LoginChoiceLabels,
    LoginChoiceResolver,
    NextgisQgisUserAvailability,
)


class ConnectionSwitcherToolButton(QToolButton):
    middle_pressed = pyqtSignal()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            event.accept()
            self.middle_pressed.emit()
            return

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.MiddleButton:
            event.accept()
            return

        super().mouseReleaseEvent(event)


class ConnectionSwitchMenu(QMenu):
    switch_requested = pyqtSignal(str, object)

    def __init__(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.__build(connections, current_connection_id)

    def __build(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
    ) -> None:
        if len(connections) == 0:
            empty_action = self.addAction(self.tr("No connections configured"))
            empty_action.setEnabled(False)
            return

        connection_group = QActionGroup(self)
        connection_group.setExclusive(True)
        connection_group.triggered.connect(self.__on_connection_triggered)

        for connection in connections:
            connection_menu = QMenu(connection.name, self)
            connection_action = connection_menu.menuAction()
            is_current = connection.id == current_connection_id
            connection_action.setCheckable(is_current)
            connection_action.setChecked(is_current)
            connection_font = connection_action.font()
            connection_font.setBold(is_current)
            connection_action.setFont(connection_font)
            connection_action.setToolTip(connection.url)
            connection_group.addAction(connection_action)
            self.addMenu(connection_menu)
            is_default_auth_available = self.__add_login_choices(
                connection_menu,
                connection,
            )
            connection_action.setData(
                (
                    connection.id,
                    connection.auth_config_id,
                    is_default_auth_available,
                )
            )

    def __add_login_choices(
        self,
        connection_menu: QMenu,
        connection: NgwConnection,
    ) -> bool:
        resolver = LoginChoiceResolver(
            connection.url,
            is_edit=True,
            filter_by_resource=True,
            labels=LoginChoiceLabels(
                nextgis_qgis_user=self.tr("NextGIS QGIS User"),
                saved_user=self.tr("Saved user"),
            ),
        )
        selected_auth_config_id = connection.auth_config_id or ""
        nextgis_choices, basic_choices = resolver.existing_choices(
            selected_auth_config_id
        )
        choices = [
            LoginChoice(LoginChoiceKind.GUEST, self.tr("Guest")),
            *nextgis_choices,
            *basic_choices,
        ]

        user_group = QActionGroup(connection_menu)
        user_group.setExclusive(True)
        user_group.triggered.connect(self.__on_user_triggered)

        is_default_auth_available = False
        for choice in choices:
            action = connection_menu.addAction(choice.title)
            action.setCheckable(True)
            is_selected = choice.auth_config_id == connection.auth_config_id
            action.setChecked(is_selected)
            action.setData((connection.id, choice.auth_config_id))
            is_available = self.__is_choice_available(choice)
            action.setEnabled(is_available)
            user_group.addAction(action)
            if is_selected:
                is_default_auth_available = is_available

        return is_default_auth_available

    def __is_choice_available(self, choice: LoginChoice) -> bool:
        if choice.method == "NextGIS" or choice.auth_config_id == "NextGIS":
            return NextgisQgisUserAvailability.is_available()

        return True

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        action = self.actionAt(event.pos())
        if (
            event.button() == Qt.MouseButton.LeftButton
            and action is not None
            and action.menu() is not None
        ):
            _, _, is_default_auth_available = cast(
                Tuple[str, Optional[str], bool],
                action.data(),
            )
            if is_default_auth_available:
                self.close()
                action.trigger()
                event.accept()
                return

        super().mouseReleaseEvent(event)

    @pyqtSlot(QAction)
    def __on_connection_triggered(self, action: QAction) -> None:
        connection_id, auth_config_id, is_default_auth_available = cast(
            Tuple[str, Optional[str], bool],
            action.data(),
        )
        if not is_default_auth_available:
            return

        self.switch_requested.emit(connection_id, auth_config_id)

    @pyqtSlot(QAction)
    def __on_user_triggered(self, action: QAction) -> None:
        connection_id, auth_config_id = cast(
            Tuple[str, Optional[str]],
            action.data(),
        )
        self.switch_requested.emit(connection_id, auth_config_id)
