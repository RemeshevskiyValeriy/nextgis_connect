from typing import Optional

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (
    QBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QWidget,
)

from nextgis_connect.shared.buttons import CancelButton
from nextgis_connect.shared.graphics.decorator import NextgisDecorator
from nextgis_connect.tree_widget.overlay.state import (
    OverlayAction,
    OverlayButtonState,
    OverlayState,
)
from nextgis_connect.tree_widget.overlay.widgets.surface import (
    OverlaySurfaceWidget,
)


class LoadingOverlayWidget(OverlaySurfaceWidget):
    """Overlay card for long-running loading and cancellation states."""

    _PROGRESS_CANCEL_SPACING = 6
    _MINIMUM_PROGRESS_CANCEL_SPACING = 2
    _LAYOUT_RESERVE = 24

    action_requested = pyqtSignal(object)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._title_label = QLabel(self._content_widget)
        title_font = self._title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        self._title_label.setFont(title_font)
        self._title_label.setWordWrap(True)
        self._title_label.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding,
            QSizePolicy.Policy.Fixed,
        )

        self._progress_layout = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self._progress_layout.setContentsMargins(0, 0, 0, 0)
        self._progress_layout.setSpacing(self._PROGRESS_CANCEL_SPACING)

        self._progress_bar = QProgressBar(self._content_widget)
        self._progress_bar.setMinimum(0)
        self._progress_bar.setMaximum(0)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setPalette(
            NextgisDecorator.progress_palette(self._progress_bar.palette())
        )
        self._progress_bar.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self._cancel_button = CancelButton(self._content_widget)
        self._cancel_button.hide()
        self._cancel_button.clicked.connect(self._emit_cancel_action)

        self._message_label = QLabel(self._content_widget)
        self._message_label.setWordWrap(True)

        self._details_label = QLabel(self._content_widget)
        self._details_label.setWordWrap(True)

        self._progress_layout.addWidget(self._progress_bar)
        self._progress_layout.addWidget(self._cancel_button)

        self._content_layout.addWidget(self._title_label)
        self._content_layout.addLayout(self._progress_layout)
        self._content_layout.addWidget(self._message_label)
        self._content_layout.addWidget(self._details_label)

        self._cancel_action = OverlayButtonState()
        self._progress_direction = QBoxLayout.Direction.LeftToRight

    def set_state(self, state: OverlayState) -> None:
        """Apply a new state to the loading overlay."""
        self.set_draw_background(state.draw_background)
        self.set_logo_action(state.logo_action)

        self._title_label.setText(self._display_text(state.title))
        self._message_label.setText(self._display_text(state.message))
        self._details_label.setVisible(bool(state.details))
        self._details_label.setText(self._display_text(state.details or ""))

        self._cancel_action = state.secondary_action
        is_cancel_visible = state.secondary_action.action != OverlayAction.NONE
        self._cancel_button.setVisible(is_cancel_visible)
        self._cancel_button.set_waiting(state.cancel_pending)
        if is_cancel_visible:
            tooltip = (
                self.tr("Waiting for cancellation to finish.")
                if state.cancel_pending
                else state.secondary_action.tooltip
                or self.tr("Cancel current operation.")
            )
            self._cancel_button.setToolTip(tooltip)
        else:
            self._cancel_button.setToolTip("")

        self.sync_layout()

    def _horizontal_content_width_for_preferred_layout(self) -> int:
        if self._cancel_button.isHidden():
            return 0

        return (
            self._progress_bar.minimumSizeHint().width()
            + self._PROGRESS_CANCEL_SPACING
            + self._cancel_button.minimumSizeHint().width()
            + self._LAYOUT_RESERVE
        )

    def _update_responsive_layout(
        self,
        content_width: int,
        card_width: int,
    ) -> None:
        del card_width
        progress_height = self._progress_bar.sizeHint().height()
        if progress_height > 0:
            self._cancel_button.set_button_height(progress_height)

        required_width = self._horizontal_content_width_for_preferred_layout()
        if self._cancel_button.isHidden() or content_width >= required_width:
            direction = QBoxLayout.Direction.LeftToRight
            spacing = self._PROGRESS_CANCEL_SPACING
        else:
            direction = QBoxLayout.Direction.TopToBottom
            spacing = self._MINIMUM_PROGRESS_CANCEL_SPACING

        self._progress_direction = direction
        if self._progress_layout.direction() != direction:
            self._progress_layout.setDirection(direction)

        if self._progress_layout.spacing() != spacing:
            self._progress_layout.setSpacing(spacing)

        self._progress_layout.invalidate()

    def _minimum_content_width_for_readable_layout(self) -> int:
        minimum_width = self._progress_bar.minimumSizeHint().width()
        if not self._cancel_button.isHidden():
            minimum_width = max(
                minimum_width,
                self._cancel_button.minimumSizeHint().width(),
            )

        return minimum_width

    def _prepare_content_for_minimum_layout(self) -> None:
        self._progress_direction = QBoxLayout.Direction.TopToBottom
        if self._progress_layout.direction() != self._progress_direction:
            self._progress_layout.setDirection(self._progress_direction)

        if self._progress_layout.spacing() != (
            self._MINIMUM_PROGRESS_CANCEL_SPACING
        ):
            self._progress_layout.setSpacing(
                self._MINIMUM_PROGRESS_CANCEL_SPACING
            )

        self._progress_layout.invalidate()

    def _prepare_content_for_layout(self) -> None:
        self._progress_direction = QBoxLayout.Direction.LeftToRight
        if self._progress_layout.direction() != self._progress_direction:
            self._progress_layout.setDirection(self._progress_direction)

        if self._progress_layout.spacing() != self._PROGRESS_CANCEL_SPACING:
            self._progress_layout.setSpacing(self._PROGRESS_CANCEL_SPACING)

    def _emit_cancel_action(self) -> None:
        if self._cancel_button.is_waiting():
            return

        if self._cancel_action.action == OverlayAction.NONE:
            return

        self.action_requested.emit(self._cancel_action.action)

    def _emit_logo_action(self) -> None:
        if self._logo_action == OverlayAction.NONE:
            return

        self.action_requested.emit(self._logo_action)
