from typing import Optional

from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QStackedLayout, QWidget

from nextgis_connect.tree_widget.overlay.state import OverlayKind, OverlayState

from .action import ActionOverlayWidget
from .loading import LoadingOverlayWidget


class OverlayHostWidget(QWidget):
    action_requested = pyqtSignal(object)

    @classmethod
    def minimum_overlay_height(cls) -> int:
        return max(
            ActionOverlayWidget.MINIMUM_OVERLAY_HEIGHT,
            LoadingOverlayWidget.MINIMUM_OVERLAY_HEIGHT,
        )

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setMinimumHeight(self.minimum_overlay_height())

        self._empty_widget = QWidget(self)
        self._action_overlay = ActionOverlayWidget(self)
        self._loading_overlay = LoadingOverlayWidget(self)
        self._current_kind = OverlayKind.NONE

        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        self._stack.addWidget(self._empty_widget)
        self._stack.addWidget(self._action_overlay)
        self._stack.addWidget(self._loading_overlay)

        self._action_overlay.action_requested.connect(
            self.action_requested.emit
        )
        self._loading_overlay.action_requested.connect(
            self.action_requested.emit
        )
        self.hide()

    def set_overlay_state(self, state: OverlayState) -> None:
        if state.kind == OverlayKind.NONE:
            self._reset_overlay_growth()
            self._current_kind = OverlayKind.NONE
            self.hide()
            self._stack.setCurrentWidget(self._empty_widget)
            return

        self.show()
        if state.kind == OverlayKind.LOADING:
            if self._current_kind != OverlayKind.LOADING:
                self._loading_overlay.reset_card_growth()

            self._current_kind = state.kind
            self._loading_overlay.set_state(state)
            self._stack.setCurrentWidget(self._loading_overlay)
            self._loading_overlay.sync_layout()
            QTimer.singleShot(0, self._loading_overlay.sync_layout)
            return

        if self._current_kind != state.kind:
            self._action_overlay.reset_card_growth()

        self._current_kind = state.kind
        self._action_overlay.set_state(state)
        self._stack.setCurrentWidget(self._action_overlay)
        self._action_overlay.sync_layout()
        QTimer.singleShot(0, self._action_overlay.sync_layout)

    def _reset_overlay_growth(self) -> None:
        self._action_overlay.reset_card_growth()
        self._loading_overlay.reset_card_growth()
