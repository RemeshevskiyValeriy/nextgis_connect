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

"""Qt model for managing attachments.

This module defines a simple container dataclass :class:`Attachment` and a
Qt list model :class:`AttachmentsModel` that exposes the attachment data to
Qt views. The model provides a custom role for description text in addition
to the standard display role (name).
"""

from dataclasses import replace
from enum import Enum, IntEnum
from typing import Any, Dict, List, Optional, Union

from qgis.PyQt.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    QObject,
    Qt,
    QVariant,
    pyqtSignal,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QPixmap

from nextgis_connect.features.synchronization.presentation.attachments.attachment_icon_provider import (
    AttachmentIconProvider,
)
from nextgis_connect.legacy.detached_editing.identification.settings import (
    IdentificationSettings,
)
from nextgis_connect.legacy.detached_editing.utils import AttachmentMetadata
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.utils import human_readable_size
from nextgis_connect.shared.types import AttachmentId


class AttachmentLoadingKind(str, Enum):
    FILE = "file"
    PREVIEW = "preview"


class AttachmentsModel(QAbstractListModel):
    """Provide a Qt list model for :class:`Attachment` objects.

    The model supports displaying the attachment name (``DisplayRole``) and
    exposing the description through a custom role ``DESCRIPTION``. Both name
    and description can be edited. Convenience methods allow adding and
    removing attachments.

    :param attachments: Optional initial list of attachments.
    :param parent: Optional QObject parent.
    """

    class Roles(IntEnum):
        ATTACHMENT = Qt.ItemDataRole.UserRole + 1
        NAME = Qt.ItemDataRole.UserRole + 2
        DESCRIPTION = Qt.ItemDataRole.UserRole + 3
        MIME_TYPE = Qt.ItemDataRole.UserRole + 4
        SIZE = Qt.ItemDataRole.UserRole + 5
        IS_CACHED = Qt.ItemDataRole.UserRole + 6
        IS_LOADING = Qt.ItemDataRole.UserRole + 7
        LOADING_PROGRESS = Qt.ItemDataRole.UserRole + 8
        LOADING_KIND = Qt.ItemDataRole.UserRole + 9

    attachment_added = pyqtSignal(AttachmentId)
    attachment_updated = pyqtSignal(AttachmentId)
    attachment_removed = pyqtSignal(AttachmentId)

    _attachments: List[AttachmentMetadata]

    def __init__(
        self,
        attachments: Optional[List[AttachmentMetadata]] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._attachments = list(attachments) if attachments else []
        self._is_cached = dict()
        self._icons_cache: Dict[AttachmentId, Any] = {}
        self._loading_progress_by_attachment_id: Dict[AttachmentId, float] = {}
        self._loading_kind_by_attachment_id: Dict[
            AttachmentId, AttachmentLoadingKind
        ] = {}
        self._is_editable = False
        self._is_initialized = False
        self._icon_provider = AttachmentIconProvider()
        self.update_cached_states()

    @property
    def is_initialized(self) -> bool:
        return self._is_initialized

    def set_editable(self, editable: bool) -> None:
        """Set whether the model is editable.

        :param editable: ``True`` to enable editing, ``False`` to disable.
        """
        if self._is_editable == editable:
            return

        self._is_editable = editable

        if not self._attachments:
            return

        top_left = self.index(0)
        bottom_right = self.index(len(self._attachments) - 1)
        self.dataChanged.emit(top_left, bottom_right, [])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        """Return number of rows in the model.

        :param parent: Unused parent index.
        :return: Row count.
        """
        return len(self._attachments)

    def index_for_attachment_id(self, aid: AttachmentId) -> QModelIndex:
        """Return model index for attachment identifier.

        :param aid: Attachment identifier.
        :return: Model index or invalid index if not found.
        """
        for row, attachment in enumerate(self._attachments):
            if attachment.aid == aid:
                return self.index(row)
        return QModelIndex()

    def data(
        self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole
    ) -> Any:
        """Return data for index / role.

        :param index: Target model index.
        :param role: Qt role enumerator.
        :return: Role specific value or ``QVariant()`` if invalid.
        """
        if not index.isValid() or index.row() >= len(self._attachments):
            return QVariant()

        attachment = self._attachments[index.row()]

        if role == Qt.ItemDataRole.DisplayRole:
            display_text = attachment.name or ""
            if attachment.size:
                display_text += f" ({human_readable_size(attachment.size)})"
            return display_text
        if role == Qt.ItemDataRole.ToolTipRole:
            return attachment.description
        if role == Qt.ItemDataRole.DecorationRole:
            return self._decoration(attachment.aid)
        if role == self.Roles.NAME:
            return attachment.name or ""
        if role == self.Roles.DESCRIPTION:
            return attachment.description
        if role == self.Roles.ATTACHMENT:
            return attachment
        if role == self.Roles.MIME_TYPE:
            return attachment.mime_type or ""
        if role == self.Roles.SIZE:
            return attachment.size
        if role == self.Roles.IS_CACHED:
            return self._is_cached.get(attachment.aid, False)
        if role == self.Roles.IS_LOADING:
            return attachment.aid in self._loading_progress_by_attachment_id
        if role == self.Roles.LOADING_PROGRESS:
            return self._loading_progress_by_attachment_id.get(attachment.aid)
        if role == self.Roles.LOADING_KIND:
            loading_kind = self._loading_kind_by_attachment_id.get(
                attachment.aid
            )
            return loading_kind.value if loading_kind is not None else ""

        return QVariant()

    def setData(
        self,
        index: QModelIndex,
        value: Any,
        role: int = Qt.ItemDataRole.EditRole,
    ) -> bool:
        """Update data for an index.

        Supports editing name (``DisplayRole``/``EditRole``) and description
        (``DESCRIPTION`` role). Emits ``dataChanged`` when successful.

        :param index: Index to modify.
        :param value: New value.
        :param role: Role representing which field to update.
        :return: ``True`` if updated else ``False``.
        """
        if not index.isValid() or index.row() >= len(self._attachments):
            return False

        attachment = self._attachments[index.row()]
        modified = False

        if role == self.Roles.NAME:
            if isinstance(value, str) and value != attachment.name:
                self._icons_cache.pop(attachment.aid, None)
                self._attachments[index.row()] = replace(
                    attachment, name=value
                )
                modified = True
                logger.debug("Attachment name updated: %s", value)
        elif role == self.Roles.DESCRIPTION:
            if isinstance(value, str) and value != attachment.description:
                self._attachments[index.row()] = replace(
                    attachment, description=value
                )
                modified = True
                logger.debug("Attachment description updated: %s", value)

        if modified:
            self.dataChanged.emit(index, index, [role])
            self.attachment_updated.emit(attachment.aid)

        return modified

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        """Return item flags for index.

        :param index: Index.
        :return: Flags enabling editing when valid.
        """
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags

        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
        if self._is_editable:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def roleNames(self) -> Dict[int, QByteArray]:
        """Return mapping of custom role integers to byte names.

        :return: Role mapping dictionary.
        """
        roles = super().roleNames()
        roles[int(self.Roles.DESCRIPTION)] = QByteArray(b"description")
        roles[int(self.Roles.ATTACHMENT)] = QByteArray(b"attachment")
        roles[int(self.Roles.IS_LOADING)] = QByteArray(b"is_loading")
        roles[int(self.Roles.LOADING_PROGRESS)] = QByteArray(
            b"loading_progress"
        )
        roles[int(self.Roles.LOADING_KIND)] = QByteArray(b"loading_kind")
        return roles

    # --- Convenience methods ------------------------------------------

    def set_attachments(
        self,
        attachments: List[AttachmentMetadata],
    ) -> None:
        """Set the entire list of attachments.

        :param attachments: New list of attachments.
        """
        self.beginResetModel()
        self._attachments = list(attachments)
        self._loading_progress_by_attachment_id.clear()
        self._loading_kind_by_attachment_id.clear()
        self._is_initialized = True
        self.update_cached_states(emit_changes=False)
        self.endResetModel()

    def clear_attachments(self) -> None:
        """Reset the model by clearing all attachments and cached states."""
        self.beginResetModel()
        self._attachments.clear()
        self._is_cached.clear()
        self._loading_progress_by_attachment_id.clear()
        self._loading_kind_by_attachment_id.clear()
        self._is_initialized = False
        self._icons_cache.clear()
        self.endResetModel()

    def add_attachment(self, attachment: AttachmentMetadata) -> None:
        """Add a new attachment to the model.

        :param attachment: Attachment to add.
        """
        position = len(self._attachments)
        self.beginInsertRows(QModelIndex(), position, position)
        self._attachments.append(attachment)
        self._is_cached[attachment.aid] = (
            attachment.file_path.exists()
            if attachment.file_path is not None
            else False
        )
        self.endInsertRows()

        self.attachment_added.emit(attachment.aid)

    def update_attachment(self, attachment: AttachmentMetadata) -> None:
        """Update an existing attachment in the model.

        :param attachment: Attachment to update.
        """
        for row, existing_attachment in enumerate(self._attachments):
            if existing_attachment.aid == attachment.aid:
                self._icons_cache.pop(attachment.aid, None)
                self._attachments[row] = attachment
                self._is_cached[attachment.aid] = (
                    attachment.file_path.exists()
                    if attachment.file_path is not None
                    else False
                )
                index = self.index(row)
                self.dataChanged.emit(index, index)
                self.attachment_updated.emit(attachment.aid)
                return

    def remove_attachment(self, attachment_id: AttachmentId) -> None:
        """Remove attachment by its identifier.

        :param attachment_id: Attachment identifier.
        """
        for row, attachment in enumerate(self._attachments):
            if attachment.aid == attachment_id:
                self.removeRow(row)
                return

    def removeRow(self, row: int, parent: QModelIndex = QModelIndex()) -> bool:  # noqa: B008
        self.beginRemoveRows(QModelIndex(), row, row)
        attachment_id = self._attachments[row].aid
        del self._attachments[row]
        del self._is_cached[attachment_id]
        self._loading_progress_by_attachment_id.pop(attachment_id, None)
        self._loading_kind_by_attachment_id.pop(attachment_id, None)
        self.endRemoveRows()

        self.attachment_removed.emit(attachment_id)

        return True

    @pyqtSlot()
    def clear(self) -> None:
        """Remove all attachments."""
        if not self._attachments:
            return
        last = len(self._attachments) - 1
        self.beginRemoveRows(QModelIndex(), 0, last)
        self._attachments.clear()
        self._is_cached.clear()
        self._loading_progress_by_attachment_id.clear()
        self._loading_kind_by_attachment_id.clear()
        self.endRemoveRows()

    @pyqtSlot()
    def update_cached_states(self, emit_changes: bool = True) -> None:
        for attachment in self._attachments:
            if attachment.aid in self._loading_progress_by_attachment_id:
                continue

            self._is_cached[attachment.aid] = (
                attachment.file_path.exists()
                if attachment.file_path is not None
                else False
            )
        self._icons_cache.clear()
        if emit_changes and self._attachments:
            top_left = self.index(0)
            bottom_right = self.index(len(self._attachments) - 1)
            self.dataChanged.emit(
                top_left,
                bottom_right,
                [
                    Qt.ItemDataRole.DecorationRole,
                    int(self.Roles.IS_CACHED),
                ],
            )

    def set_attachment_loading_progress(
        self,
        attachment_id: AttachmentId,
        progress: Optional[float],
        loading_kind: Union[
            AttachmentLoadingKind, str
        ] = AttachmentLoadingKind.FILE,
    ) -> None:
        """Set or clear loading progress for an attachment."""
        previous_progress = self._loading_progress_by_attachment_id.get(
            attachment_id
        )
        if progress is None:
            has_loading_progress = (
                attachment_id in self._loading_progress_by_attachment_id
            )
            has_loading_kind = (
                attachment_id in self._loading_kind_by_attachment_id
            )
            if not has_loading_progress and not has_loading_kind:
                return
            self._loading_progress_by_attachment_id.pop(attachment_id, None)
            self._loading_kind_by_attachment_id.pop(attachment_id, None)
        else:
            progress = max(0.0, min(100.0, float(progress)))
            normalized_loading_kind = self._normalize_loading_kind(
                loading_kind
            )
            previous_loading_kind = self._loading_kind_by_attachment_id.get(
                attachment_id
            )
            if (
                previous_progress == progress
                and previous_loading_kind == normalized_loading_kind
            ):
                return
            self._loading_progress_by_attachment_id[attachment_id] = progress
            self._loading_kind_by_attachment_id[attachment_id] = (
                normalized_loading_kind
            )

        index = self.index_for_attachment_id(attachment_id)
        if not index.isValid():
            return

        self.dataChanged.emit(
            index,
            index,
            [
                Qt.ItemDataRole.DecorationRole,
                int(self.Roles.IS_LOADING),
                int(self.Roles.LOADING_PROGRESS),
                int(self.Roles.LOADING_KIND),
            ],
        )

    def _normalize_loading_kind(
        self,
        loading_kind: Union[AttachmentLoadingKind, str],
    ) -> AttachmentLoadingKind:
        if isinstance(loading_kind, AttachmentLoadingKind):
            return loading_kind

        try:
            return AttachmentLoadingKind(str(loading_kind))
        except ValueError:
            return AttachmentLoadingKind.FILE

    def attachment_by_id(self, aid: int) -> Optional[AttachmentMetadata]:
        """Return attachment by identifier.

        :param aid: Attachment identifier.
        :return: Attachment or ``None`` if not found.
        """
        for attachment in self._attachments:
            if attachment.aid == aid:
                return attachment
        return None

    def _decoration(self, aid: int) -> Any:
        """Return cached decoration for attachment id.

        :param aid: Attachment identifier.
        :return: Icon or pixmap object.
        """
        if aid in self._icons_cache:
            return self._icons_cache[aid]

        attachment = self.attachment_by_id(aid)
        if not attachment:
            return None

        thumbnail = self._thumbnail(attachment)
        if thumbnail is not None:
            self._icons_cache[aid] = thumbnail
            return thumbnail

        icon = self._icon_provider.icon_for_file_name(attachment.name)
        self._icons_cache[aid] = icon
        return icon

    def _thumbnail(self, attachment: AttachmentMetadata) -> Optional[QPixmap]:
        if not self._is_image(attachment):
            return None

        if (
            attachment.thumbnail_path is None
            or not attachment.thumbnail_path.exists()
        ):
            return None

        pixmap = QPixmap(str(attachment.thumbnail_path))
        if pixmap.isNull():
            return None

        return pixmap

    def _is_image(self, attachment: AttachmentMetadata) -> bool:
        mime_type = attachment.mime_type or ""
        settings = IdentificationSettings()
        return (
            mime_type in settings.attachment_thumbnail_mime_types
            or mime_type.startswith("image/")
        )
