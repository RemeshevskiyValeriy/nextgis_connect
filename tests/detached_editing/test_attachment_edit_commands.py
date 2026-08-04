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

from collections import defaultdict
from typing import DefaultDict, Dict, List, Set, Tuple

from nextgis_connect.legacy.detached_editing.container.editing.commands.attachment_remove import (
    AttachmentRemoveCommand,
)
from nextgis_connect.legacy.detached_editing.container.editing.commands.attachment_update import (
    AttachmentUpdateCommand,
)
from nextgis_connect.legacy.detached_editing.utils import AttachmentMetadata
from nextgis_connect.platform.qgis.compat import QgsFeatureId
from nextgis_connect.shared.types import AttachmentId


class _Signal:
    def __init__(self) -> None:
        self.calls: List[Tuple[QgsFeatureId, AttachmentId]] = []

    def emit(
        self, feature_id: QgsFeatureId, attachment_id: AttachmentId
    ) -> None:
        self.calls.append((feature_id, attachment_id))


class _EditBuffer:
    def __init__(self) -> None:
        self._added_attachments: DefaultDict[
            QgsFeatureId, Dict[AttachmentId, AttachmentMetadata]
        ] = defaultdict(dict)
        self._updated_attachments: DefaultDict[
            QgsFeatureId, Dict[AttachmentId, AttachmentMetadata]
        ] = defaultdict(dict)
        self._removed_attachments: DefaultDict[
            QgsFeatureId, Set[AttachmentId]
        ] = defaultdict(set)
        self.attachment_added = _Signal()
        self.attachment_updated = _Signal()
        self.attachment_removed = _Signal()

    @property
    def updated_attachments(
        self,
    ) -> DefaultDict[QgsFeatureId, Dict[AttachmentId, AttachmentMetadata]]:
        return self._updated_attachments


class _DetachedLayer:
    def __init__(self) -> None:
        self.edit_buffer = _EditBuffer()


def test_new_attachment_description_update_stays_in_added_collection(
    qgis_app,
) -> None:
    del qgis_app

    detached_layer = _DetachedLayer()
    old_attachment = AttachmentMetadata(
        fid=7,
        aid=-1,
        name="photo.jpg",
    )
    new_attachment = AttachmentMetadata(
        fid=7,
        aid=-1,
        name="photo.jpg",
        description="New description",
    )
    detached_layer.edit_buffer._added_attachments[7][-1] = old_attachment
    command = AttachmentUpdateCommand(
        detached_layer,
        old_attachment,
        new_attachment,
    )

    command.redo()

    assert (
        detached_layer.edit_buffer._added_attachments[7][-1].description
        == "New description"
    )
    assert -1 not in detached_layer.edit_buffer._updated_attachments[7]
    assert detached_layer.edit_buffer.attachment_updated.calls == [(7, -1)]

    command.undo()

    assert (
        detached_layer.edit_buffer._added_attachments[7][-1] == old_attachment
    )
    assert -1 not in detached_layer.edit_buffer._updated_attachments[7]
    assert detached_layer.edit_buffer.attachment_updated.calls == [
        (7, -1),
        (7, -1),
    ]


def test_new_attachment_remove_drops_added_attachment_only(qgis_app) -> None:
    del qgis_app

    detached_layer = _DetachedLayer()
    attachment = AttachmentMetadata(
        fid=7,
        aid=-1,
        name="photo.jpg",
    )
    detached_layer.edit_buffer._added_attachments[7][-1] = attachment
    command = AttachmentRemoveCommand(detached_layer, attachment)

    command.redo()

    assert -1 not in detached_layer.edit_buffer._added_attachments[7]
    assert -1 not in detached_layer.edit_buffer._removed_attachments[7]
    assert detached_layer.edit_buffer.attachment_removed.calls == [(7, -1)]

    command.undo()

    assert detached_layer.edit_buffer._added_attachments[7][-1] == attachment
    assert -1 not in detached_layer.edit_buffer._removed_attachments[7]
    assert detached_layer.edit_buffer.attachment_added.calls == [(7, -1)]
