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

from pathlib import Path
from typing import Optional

from nextgis_connect.features.synchronization.infrastructure.storage.attachment_store import (
    AttachmentStore,
)
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    BlobRef,
    StorageEntry,
    StorageEntryProtection,
    StorageEntryState,
)


class AttachmentLifecycle:
    """Apply copy-on-write attachment lifecycle transitions."""

    def __init__(self, attachment_store: AttachmentStore) -> None:
        """Initialize attachment lifecycle service."""
        self._attachment_store = attachment_store

    def stage_new_file(
        self,
        attachment_key: AttachmentKey,
        source_path: Path,
        *,
        local_blob_uuid: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> BlobRef:
        """Stage a new local attachment file."""
        return self._attachment_store.stage_blob(
            attachment_key,
            source_path,
            local_blob_uuid=local_blob_uuid,
            extension=extension,
            pending_operation=AttachmentOperation.CREATE,
        )

    def stage_replacement(
        self,
        attachment_key: AttachmentKey,
        source_path: Path,
        *,
        committed_blob_entry_id: Optional[int],
        local_blob_uuid: Optional[str] = None,
        extension: Optional[str] = None,
    ) -> BlobRef:
        """Stage a replacement without overwriting committed blob."""
        return self._attachment_store.stage_blob(
            attachment_key,
            source_path,
            local_blob_uuid=local_blob_uuid,
            extension=extension,
            pending_operation=AttachmentOperation.UPDATE_FILE,
            committed_blob_entry_id=committed_blob_entry_id,
        )

    def mark_uploaded_pending_commit(
        self,
        attachment_key: AttachmentKey,
        *,
        staged_blob_entry_id: int,
        fileobj: object,
        ngw_aid: Optional[int],
    ) -> None:
        """Mark a staged blob as uploaded but not server-committed."""
        storage_index = self._attachment_store.storage_index
        entry = storage_index.find_entry_by_id(staged_blob_entry_id)
        if entry is None:
            return

        storage_index.update_entry(
            StorageEntry(
                id=entry.id,
                storage_key=entry.storage_key,
                kind=entry.kind,
                relative_path=entry.relative_path,
                instance_uuid=entry.instance_uuid,
                resource_id=entry.resource_id,
                size_bytes=entry.size_bytes,
                sha256=entry.sha256,
                state=StorageEntryState.UPLOADED_PENDING_COMMIT,
                protection=StorageEntryProtection.DIRTY,
            )
        )
        storage_index.upsert_blob_remote_map(
            blob_entry_id=staged_blob_entry_id,
            fileobj=fileobj,
            ngw_aid=ngw_aid,
            sha256=entry.sha256,
            mime_type=None,
            original_name=None,
        )
