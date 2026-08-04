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

from typing import Optional, cast

from qgis.PyQt.QtCore import QAbstractItemModel, QModelIndex, Qt, pyqtSignal
from qgis.PyQt.QtGui import QContextMenuEvent, QKeyEvent, QMouseEvent
from qgis.PyQt.QtWidgets import QListView, QWidget

from nextgis_connect.features.synchronization.presentation.attachments.attachment_delegate import (
    AttachmentDelegate,
)


class AttachmentsView(QListView):
    """Render and manage the list of feature attachments.

    Coordinate attachment-related user interactions, including opening,
    caching, exporting, and showing attachments in the file manager.
    Provide keyboard and context menu handling for the underlying delegate.

    :ivar model_changed: Emit when the attached model changes.
    :ivar open_attachment: Emit when the user requests opening an attachment.
    :ivar cache_attachment: Emit when the user requests caching an attachment.
    :ivar show_in_folder: Emit when the user requests revealing an attachment.
    :ivar save_as: Emit when the user requests saving an attachment.
    :ivar delete_attachment: Emit when the user requests deleting an
        attachment.
    """

    model_changed = pyqtSignal(object)  # Optional[QAbstractItemModel]

    open_attachment = pyqtSignal(QModelIndex)
    cache_attachment = pyqtSignal(QModelIndex)
    show_in_folder = pyqtSignal(QModelIndex)
    save_as = pyqtSignal(QModelIndex)
    copy_attachment = pyqtSignal(QModelIndex)
    delete_attachment = pyqtSignal(QModelIndex)

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """Initialize the attachments view.

        :param parent: Parent widget owning the view.
        """
        super().__init__(parent)

        self._delegate = AttachmentDelegate(self)
        self._delegate.open_attachment.connect(self.open_attachment)
        self._delegate.cache_attachment.connect(self.cache_attachment)
        self._delegate.show_in_folder.connect(self.show_in_folder)
        self._delegate.save_as.connect(self.save_as)
        self._delegate.copy_attachment.connect(self.copy_attachment)
        self._delegate.delete_attachment.connect(self.delete_attachment)
        self.setItemDelegate(self._delegate)

        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.setAcceptDrops(False)  # wrapper handles DnD

        self.doubleClicked.connect(self.open_attachment)

        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)

        self._read_only = True

    def set_read_only(self, read_only: bool) -> None:
        """Set the read-only state of the attachments view.

        :param read_only: ``True`` to set the view to read-only mode,
            ``False`` to make it editable.
        """
        if read_only:
            self.close_current_editor()

        self._read_only = read_only

    def close_current_editor(self) -> None:
        """Close the inline attachment editor, if it is open."""
        self._delegate.close_current_editor()

    def setModel(self, model: Optional[QAbstractItemModel]) -> None:
        """Attach a model and notify listeners about the change.

        :param model: Model providing attachment items.
        """
        super().setModel(model)
        self.model_changed.emit(model)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Handle keyboard shortcuts for selection and inline editing.

        :param event: Key event dispatched to the view.
        """
        if (
            event.key() == Qt.Key.Key_Escape
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
        ):
            if self._delegate.has_current_editor():
                self._delegate.close_current_editor()
            else:
                self.selectionModel().clear()

        elif (
            event.key() == Qt.Key.Key_F2
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and not self._read_only
            and self.currentIndex().isValid()
        ):
            self.edit(self.currentIndex())
        elif (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() == Qt.KeyboardModifier.NoModifier
            and self.currentIndex().isValid()
            and not self._delegate.has_current_editor()
        ):
            self.open_attachment.emit(self.currentIndex())
        else:
            super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Clear selection when the user clicks outside any item.

        :param event: Mouse event dispatched to the view.
        """
        if not self.indexAt(event.pos()).isValid():
            self.selectionModel().clear()

        super().mousePressEvent(event)

    def contextMenuEvent(self, event: Optional[QContextMenuEvent]) -> None:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Show the delegate context menu for the item under the cursor.

        :param event: Context menu event dispatched to the view.
        """
        if event is None:
            return

        index = self.indexAt(event.pos())
        if not index.isValid():
            self.selectionModel().clear()
            event.ignore()
            return

        self.setCurrentIndex(index)
        self.selectionModel().select(
            index,
            self.selectionModel().SelectionFlag.ClearAndSelect,
        )

        delegate = cast(AttachmentDelegate, self.itemDelegate())
        menu = delegate.build_context_menu(self, index)
        menu.exec(event.globalPos())
