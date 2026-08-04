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

from dataclasses import dataclass
from typing import Any, Optional, Tuple

from qgis.PyQt.QtCore import QModelIndex, Qt

from nextgis_connect.legacy.detached_editing.identification.attachments_model import (
    AttachmentLoadingKind,
    AttachmentsModel,
)


@dataclass(frozen=True)
class AttachmentDisplayState:
    """Store data needed to render one attachment item."""

    icon_value: Any
    attachment_identity: Optional[Tuple[int, int]]
    title: str
    description: str
    mime_type: str
    is_cached: bool
    is_loading: bool
    loading_progress: Optional[float]
    loading_kind: str = ""

    @property
    def is_preview_loading(self) -> bool:
        return self.loading_kind == AttachmentLoadingKind.PREVIEW.value

    @classmethod
    def from_index(
        cls,
        index: QModelIndex,
        *,
        for_editor: bool = False,
    ) -> "AttachmentDisplayState":
        """Build display state from a model index."""
        title_role = (
            AttachmentsModel.Roles.NAME
            if for_editor
            else Qt.ItemDataRole.DisplayRole
        )
        title_value = index.data(title_role)
        description_value = index.data(AttachmentsModel.Roles.DESCRIPTION)
        mime_type_value = index.data(AttachmentsModel.Roles.MIME_TYPE)
        progress_value = index.data(AttachmentsModel.Roles.LOADING_PROGRESS)
        loading_kind_value = index.data(AttachmentsModel.Roles.LOADING_KIND)
        attachment_value = index.data(AttachmentsModel.Roles.ATTACHMENT)
        loading_kind = (
            loading_kind_value if isinstance(loading_kind_value, str) else ""
        )
        is_loading = bool(index.data(AttachmentsModel.Roles.IS_LOADING))
        icon_value = None
        if not (
            is_loading and loading_kind == AttachmentLoadingKind.PREVIEW.value
        ):
            icon_value = index.data(Qt.ItemDataRole.DecorationRole)

        loading_progress = None
        if isinstance(progress_value, (float, int)):
            loading_progress = max(0.0, min(100.0, float(progress_value)))

        attachment_identity = None
        attachment_id = getattr(attachment_value, "aid", None)
        feature_id = getattr(attachment_value, "fid", None)
        try:
            attachment_identity = (int(feature_id), int(attachment_id))
        except (TypeError, ValueError):
            attachment_identity = None

        return cls(
            icon_value=icon_value,
            attachment_identity=attachment_identity,
            title=title_value if isinstance(title_value, str) else "",
            description=(
                description_value if isinstance(description_value, str) else ""
            ),
            mime_type=mime_type_value
            if isinstance(mime_type_value, str)
            else "",
            is_cached=bool(index.data(AttachmentsModel.Roles.IS_CACHED)),
            is_loading=is_loading,
            loading_progress=loading_progress,
            loading_kind=loading_kind,
        )
