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

from enum import IntEnum
from typing import TYPE_CHECKING, Dict, List, Optional, cast

from qgis.PyQt import sip
from qgis.PyQt.QtCore import (
    QAbstractProxyModel,
    QEvent,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QPointF,
)
from qgis.PyQt.QtGui import QInputEvent, QMouseEvent, QTabletEvent, QWheelEvent
from qgis.PyQt.QtWidgets import (
    QApplication,
    QStyleOptionViewItem,
    QWidget,
)

from nextgis_connect.platform.logging import logger

if TYPE_CHECKING:
    from nextgis_connect.ui_kit.delegates.widget_item_delegate import (
        WidgetItemDelegate,
    )


class WidgetItemDelegateEventListener(QObject):
    """Forward input events from embedded widgets to the viewport.

    Handles safe destruction notifications and regenerates input events
    in the viewport coordinate system, unless they are explicitly
    blocked by the delegate for a particular widget.

    Python port of KWidgetItemDelegateEventListener (KItemViews)

    :ivar _pool: Pool managing widgets and related state.
    """

    def __init__(
        self, pool: "WidgetItemDelegatePool", parent: Optional[QObject] = None
    ) -> None:
        """Initialize event listener.

        :param pool: Owning widget pool instance.
        :param parent: Optional QObject parent.
        """
        super().__init__(parent)
        self._pool = pool

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:  # type: ignore[override]
        """Filter widget events and forward to the view's viewport.

        :param watched: Observed object (expected to be a QWidget).
        :param event: Event to filter and possibly forward.
        :return: ``True`` if handled; otherwise calls base implementation.
        """
        widget = watched

        if not isinstance(widget, QWidget):
            return super().eventFilter(watched, event)

        DestroyType = QEvent.Type(16)  # QEvent.Type.Destroy
        if event.type() == DestroyType and not self._pool.is_clearing:
            logger.warning(
                "User of WidgetItemDelegate should not delete widgets created by createItemWidgets!"
            )
            # assume the application has kept a list of widgets and tries to
            # delete them manually they have been reparented to the view in
            # any case, so no leaking occurs
            self._pool._widget_in_index.pop(widget, None)
            if not self._pool.delegate._has_valid_item_view():
                return super().eventFilter(watched, event)

            viewport = self._pool.delegate.item_view().viewport()
            QApplication.sendEvent(viewport, event)
            return super().eventFilter(watched, event)

        if not self._pool.delegate._has_valid_item_view():
            return super().eventFilter(watched, event)

        # Forward input events to the viewport if the type is not blocked
        blocked_types = self._pool.delegate._blocked_event_types(widget)
        if not isinstance(event, QInputEvent) or event.type() in blocked_types:
            return super().eventFilter(watched, event)

        viewport = self._pool.delegate.item_view().viewport()

        try:
            if event.type() in (
                QEvent.Type.MouseMove,
                QEvent.Type.MouseButtonPress,
                QEvent.Type.MouseButtonRelease,
                QEvent.Type.MouseButtonDblClick,
            ):
                mouse_event: QMouseEvent = cast(QMouseEvent, event)
                new_mouse_event = QMouseEvent(
                    event.type(),
                    viewport.mapFromGlobal(mouse_event.globalPos()),
                    mouse_event.button(),
                    mouse_event.buttons(),
                    mouse_event.modifiers(),
                )

                QApplication.sendEvent(viewport, new_mouse_event)

            elif event.type() == QEvent.Type.Wheel:
                wheel_event: QWheelEvent = cast(QWheelEvent, event)

                new_wheel_event = QWheelEvent(
                    viewport.mapFromGlobal(wheel_event.position().toPoint()),
                    viewport.mapFromGlobal(
                        wheel_event.globalPosition().toPoint()
                    ),
                    wheel_event.pixelDelta(),
                    wheel_event.angleDelta(),
                    wheel_event.buttons(),
                    wheel_event.modifiers(),
                    wheel_event.phase(),
                    wheel_event.inverted(),
                    wheel_event.source(),
                )
                QApplication.sendEvent(viewport, new_wheel_event)

            elif event.type() in (
                QEvent.Type.TabletMove,
                QEvent.Type.TabletPress,
                QEvent.Type.TabletRelease,
                QEvent.Type.TabletEnterProximity,
                QEvent.Type.TabletLeaveProximity,
            ):
                tablet_event: QTabletEvent = cast(QTabletEvent, event)
                # Qt5/Qt6 compatibility: compute global/local positions
                if hasattr(tablet_event, "globalPosition"):
                    new_tablet_event = QTabletEvent(
                        event.type(),
                        tablet_event.pointingDevice(),  # type: ignore
                        viewport.mapFromGlobal(tablet_event.globalPosition()),  # type: ignore
                        tablet_event.globalPosition(),  # type: ignore
                        tablet_event.pressure(),  # type: ignore
                        tablet_event.xTilt(),
                        tablet_event.yTilt(),
                        tablet_event.tangentialPressure(),  # type: ignore
                        tablet_event.rotation(),
                        tablet_event.z(),
                        tablet_event.modifiers(),
                        tablet_event.button(),  # type: ignore
                        tablet_event.buttons(),
                    )
                else:
                    new_tablet_event = QTabletEvent(
                        event.type(),
                        QPointF(
                            viewport.mapFromGlobal(tablet_event.globalPos())
                        ),
                        tablet_event.globalPosF(),
                        tablet_event.deviceType(),
                        tablet_event.pointerType(),
                        tablet_event.pressure(),
                        tablet_event.xTilt(),
                        tablet_event.yTilt(),
                        tablet_event.tangentialPressure(),
                        tablet_event.rotation(),
                        tablet_event.z(),
                        tablet_event.modifiers(),
                        tablet_event.uniqueId(),
                        tablet_event.button(),
                        tablet_event.buttons(),
                    )

                QApplication.sendEvent(viewport, new_tablet_event)

            else:
                # Forward the original event
                QApplication.sendEvent(viewport, event)

        except Exception:
            # Do not break event loop on unexpected errors
            logger.exception(
                "Error forwarding event %s from widget %s to viewport",
                event,
                widget,
            )

        return super().eventFilter(watched, event)


class WidgetItemDelegatePool:
    """Manage widgets created by a widget-based item delegate.

    Stores per-index widget lists, installs event filters to forward
    input to the viewport, and updates or clears widgets on model/view
    changes.

    Python port of KWidgetItemDelegatePool (KItemViews)

    :ivar _delegate: Owning delegate instance.
    :ivar _event_listener: Event listener instance for forwarding.
    :ivar _used_widgets: Mapping from persistent index to widgets list.
    :ivar _widget_in_index: Reverse mapping from widget to index.
    :ivar _is_clearing: Internal flag to suppress warnings during clear.
    """

    class UpdateWidgetsEnum(IntEnum):
        """Control whether to update widget geometry/state."""

        UpdateWidgets = 0
        NotUpdateWidgets = 1

    def __init__(self, delegate: "WidgetItemDelegate") -> None:
        """Initialize widget pool for the provided delegate.

        :param delegate: Delegate owning this pool.
        """
        self._delegate = delegate
        self._event_listener = WidgetItemDelegateEventListener(self)
        self._used_widgets: Dict[QPersistentModelIndex, list[QWidget]] = {}
        self._widget_in_index: Dict[QWidget, QPersistentModelIndex] = {}
        self._is_clearing: bool = False

    @property
    def is_clearing(self) -> bool:
        """Return whether the pool is currently clearing widgets.

        :return: ``True`` if in clearing phase, otherwise ``False``.
        """
        return self._is_clearing

    @property
    def delegate(self) -> "WidgetItemDelegate":
        """Return the owning delegate.

        :return: Delegate associated with this pool.
        """
        return self._delegate

    def find_and_update_widgets(
        self,
        index: QPersistentModelIndex,
        option: QStyleOptionViewItem,
        updateWidgets: UpdateWidgetsEnum = UpdateWidgetsEnum.UpdateWidgets,
    ) -> List[QWidget]:
        """Return and optionally update widgets for an index.

        Creates widgets on first use, reuses them subsequently, and when
        requested updates their visible state and geometry.

        :param index: Persistent index for which to obtain widgets.
        :param option: Style option describing item rectangle/state.
        :param updateWidgets: Whether to update widget state/geometry.
        :return: List of widgets associated with the index.
        """
        result: List[QWidget] = []

        if not self._delegate._has_valid_item_view():
            return result

        if not index or not index.isValid():
            return result

        # If idx belongs to a proxy model, map to source
        model = index.model()
        if isinstance(model, QAbstractProxyModel):
            source_index = model.mapToSource(QModelIndex(index))
        else:
            source_index = QModelIndex(index)

        if not source_index.isValid():
            return result

        persistent_source_index = QPersistentModelIndex(source_index)

        if persistent_source_index in self._used_widgets:
            result = self._used_widgets[persistent_source_index]
        else:
            # Create item widgets via delegate and register them
            result = list(self._delegate._create_item_widgets(source_index))
            self._used_widgets[persistent_source_index] = result
            viewport = self._delegate.item_view().viewport()
            for widget in result:
                self._widget_in_index[widget] = persistent_source_index
                widget.setParent(viewport)
                widget.installEventFilter(self._event_listener)
                widget.setVisible(True)

        if updateWidgets == self.UpdateWidgetsEnum.UpdateWidgets:
            for widget in result:
                widget.setVisible(True)

            # Ask delegate to update widgets
            self._delegate._update_item_widgets(result, option, index)

            # Move according to option.rect
            rect = option.rect
            left = rect.left()
            top = rect.top()
            for widget in result:
                widget.move(widget.x() + left, widget.y() + top)

        return result

    def invalid_indexes_widgets(self) -> List[QWidget]:
        """Return widgets whose associated indexes are invalid.

        :return: Widgets bound to invalid or stale indexes.
        """
        result: List[QWidget] = []

        if not self._delegate._has_valid_item_view():
            return result

        # Delegate's model can be a proxy; map from source to proxy before validation
        delegate_model = self._delegate.item_view().model()
        for widget, persistent_index in list(self._widget_in_index.items()):
            index: QModelIndex

            if isinstance(delegate_model, QAbstractProxyModel):
                index = delegate_model.mapFromSource(
                    QModelIndex(persistent_index)
                )

            else:
                index = QModelIndex(persistent_index)

            if not index.isValid():
                result.append(widget)

        return result

    def full_clear(self) -> None:
        """Delete all managed widgets and reset internal mappings."""
        self._is_clearing = True

        for widget in list(self._widget_in_index.keys()):
            sip.delete(widget)

        self._is_clearing = False

        self._used_widgets.clear()
        self._widget_in_index.clear()
