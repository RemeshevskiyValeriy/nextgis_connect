from dataclasses import dataclass
from typing import Optional

from qgis.PyQt.QtCore import (
    QEvent,
    QObject,
    QPoint,
    QSize,
    Qt,
    pyqtSignal,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QMouseEvent
from qgis.PyQt.QtWidgets import QAction, QToolBar, QToolButton, QWidget


@dataclass(frozen=True)
class PluginPanelToolBarActions:
    add_to_qgis: QAction
    add_to_web_gis: QAction
    identify: QAction
    create_resource: QAction
    search: QAction
    refresh: QAction
    open_in_browser: QAction
    settings: QAction
    help: QAction


class _MiddleClickFilter(QObject):
    """Translate a complete middle-button click into a Qt signal."""

    clicked = pyqtSignal()

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._is_pressed = False

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if not isinstance(event, QMouseEvent):
            return super().eventFilter(watched, event)

        if event.button() != Qt.MouseButton.MiddleButton:
            return super().eventFilter(watched, event)

        if event.type() == QEvent.Type.MouseButtonPress:
            self._is_pressed = True
            event.accept()
            return True

        if event.type() != QEvent.Type.MouseButtonRelease:
            return super().eventFilter(watched, event)

        was_pressed = self._is_pressed
        self._is_pressed = False
        event.accept()
        if (
            was_pressed
            and isinstance(watched, QWidget)
            and watched.rect().contains(event.pos())
        ):
            self.clicked.emit()

        return True


class PluginPanelToolBar(QToolBar):
    """Display plugin panel commands using native toolbar actions."""

    settings_middle_clicked = pyqtSignal(QPoint)

    ICON_SIZE = 20

    def __init__(
        self,
        actions: PluginPanelToolBarActions,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("NgConnectPluginPanelToolBar")
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        self.setFloatable(False)
        self.setMovable(False)
        self.setIconSize(QSize(self.ICON_SIZE, self.ICON_SIZE))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        self._add_action(
            actions.add_to_qgis,
            QToolButton.ToolButtonPopupMode.InstantPopup,
        )
        self._add_action(
            actions.add_to_web_gis,
            QToolButton.ToolButtonPopupMode.InstantPopup,
        )
        self.addSeparator()
        self._add_action(actions.identify)
        self.addSeparator()
        self._add_action(
            actions.create_resource,
            QToolButton.ToolButtonPopupMode.MenuButtonPopup,
        )
        self._add_action(
            actions.search,
            QToolButton.ToolButtonPopupMode.MenuButtonPopup,
        )
        self._add_action(actions.refresh)
        self.addSeparator()
        self._add_action(actions.open_in_browser)
        self.addSeparator()
        self._settings_button = self._add_action(actions.settings)
        self._settings_middle_click_filter = _MiddleClickFilter(self)
        self._settings_middle_click_filter.clicked.connect(
            self._emit_settings_middle_clicked
        )
        self._settings_button.installEventFilter(
            self._settings_middle_click_filter
        )
        self._add_action(actions.help)

    def _add_action(
        self,
        action: QAction,
        popup_mode: Optional[QToolButton.ToolButtonPopupMode] = None,
    ) -> QToolButton:
        self.addAction(action)
        button = self.widgetForAction(action)
        if not isinstance(button, QToolButton):
            raise RuntimeError("QToolBar did not create an action button")

        if popup_mode is not None:
            button.setPopupMode(popup_mode)

        return button

    @pyqtSlot()
    def _emit_settings_middle_clicked(self) -> None:
        popup_position = self._settings_button.mapToGlobal(
            QPoint(0, self._settings_button.height())
        )
        self.settings_middle_clicked.emit(popup_position)
