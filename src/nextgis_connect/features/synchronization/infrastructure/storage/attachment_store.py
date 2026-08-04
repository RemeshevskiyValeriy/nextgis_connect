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

import uuid
from dataclasses import replace
from pathlib import Path
from typing import Optional

from nextgis_connect.platform.storage.file_store import FileStore
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    BlobRef,
    StorageEntry,
    StorageEntryKind,
    StorageEntryProtection,
    StorageEntryState,
    StorageKey,
)
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)
from nextgis_connect.platform.storage.storage_key import (
    StorageKeyFactory,
    safe_blob_file_name,
)


class AttachmentStore:
    """Manage attachment blobs and previews in local storage."""

    def __init__(self, cache_root: Path) -> None:
        """Initialize attachment store."""
        self._path_resolver = StoragePathResolver(Path(cache_root))
        self._storage_index = SqliteStorageIndex(
            self._path_resolver.index_path()
        )

    def remote_blob_key(
        self,
        instance_uuid: str,
        resource_id: int,
        fileobj: object,
    ) -> StorageKey:
        """Return the key for a remote attachment blob."""
        return StorageKeyFactory.remote_attachment_blob(
            instance_uuid,
            resource_id,
            fileobj,
        )

    def local_blob_key(
        self,
        instance_uuid: str,
        resource_id: int,
        local_blob_uuid: str,
    ) -> StorageKey:
        """Return the key for a local staged attachment blob."""
        return StorageKeyFactory.local_attachment_blob(
            instance_uuid,
            resource_id,
            local_blob_uuid,
        )

    def preview_key(
        self,
        blob_storage_key: StorageKey,
        preview_profile: str = "default",
    ) -> StorageKey:
        """Return the key for an attachment preview."""
        return StorageKeyFactory.attachment_preview(
            blob_storage_key,
            preview_profile,
        )

    def blob_path(
        self,
        storage_key: StorageKey,
        extension: Optional[str] = None,
    ) -> Path:
        """Return a path for an attachment blob."""
        return self._path_resolver.resolve(
            storage_key,
            safe_blob_file_name(extension),
        )

    def preview_path(
        self,
        blob_storage_key: StorageKey,
        preview_profile: str = "default",
    ) -> Path:
        """Return a path for an attachment preview."""
        storage_key = self.preview_key(blob_storage_key, preview_profile)
        return self._path_resolver.resolve(storage_key, "preview.jpg")

    def stage_blob(
        self,
        attachment_key: AttachmentKey,
        source_path: Path,
        *,
        local_blob_uuid: Optional[str] = None,
        extension: Optional[str] = None,
        pending_operation: AttachmentOperation = AttachmentOperation.CREATE,
        committed_blob_entry_id: Optional[int] = None,
    ) -> BlobRef:
        """Stage a new local attachment blob."""
        storage_index = self._storage_index
        previous_record = storage_index.attachment_record(attachment_key)
        previous_staged_entry_id = self._record_entry_id(
            previous_record,
            "staged_blob_entry_id",
        )
        blob_uuid = local_blob_uuid or str(uuid.uuid4())
        storage_key = self.local_blob_key(
            attachment_key.instance_uuid,
            attachment_key.resource_id,
            blob_uuid,
        )
        file_store = FileStore(self._path_resolver, storage_index)
        blob_ref = file_store.copy_from(
            storage_key,
            safe_blob_file_name(extension),
            Path(source_path),
            kind=StorageEntryKind.ATTACHMENT_BLOB,
            resource_id=attachment_key.resource_id,
            state=StorageEntryState.STAGED,
            protection=StorageEntryProtection.DIRTY,
            overwrite=False,
        )
        storage_index.upsert_attachment_record(
            attachment_key,
            committed_blob_entry_id=committed_blob_entry_id,
            staged_blob_entry_id=blob_ref.entry_id,
            active_blob_entry_id=blob_ref.entry_id,
            preview_entry_id=None,
            pending_operation=pending_operation,
        )
        if previous_staged_entry_id != blob_ref.entry_id:
            self._mark_entry_orphaned(
                storage_index,
                previous_staged_entry_id,
            )
        return blob_ref

    def discard_staged_blob(self, attachment_key: AttachmentKey) -> None:
        """Delete a staged blob and restore the committed attachment."""
        storage_index = self._storage_index
        record = storage_index.attachment_record(attachment_key)
        staged_entry_id = self._record_entry_id(
            record,
            "staged_blob_entry_id",
        )
        if staged_entry_id is None:
            return

        entry = storage_index.find_entry_by_id(staged_entry_id)
        if entry is not None:
            path = self._path_resolver.absolute_from_entry(
                entry.relative_path,
            )
            path.unlink(missing_ok=True)
            self._remove_empty_parents(path.parent)

        committed_entry_id = self._record_entry_id(
            record,
            "committed_blob_entry_id",
        )
        if committed_entry_id is None:
            storage_index.delete_attachment_record(attachment_key)
        else:
            storage_index.upsert_attachment_record(
                attachment_key,
                committed_blob_entry_id=committed_entry_id,
                staged_blob_entry_id=None,
                active_blob_entry_id=committed_entry_id,
                preview_entry_id=self._record_entry_id(
                    record,
                    "preview_entry_id",
                ),
                pending_operation=AttachmentOperation.NONE,
            )
        storage_index.delete_entry(staged_entry_id)

    def register_remote_blob(
        self,
        attachment_key: AttachmentKey,
        storage_key: StorageKey,
        path: Path,
        *,
        fileobj: object,
        ngw_aid: Optional[int],
        extension: Optional[str] = None,
        protection: StorageEntryProtection = StorageEntryProtection.NONE,
    ) -> StorageEntry:
        """Register a committed remote blob."""
        storage_index = self._storage_index
        file_store = FileStore(self._path_resolver, storage_index)
        entry = file_store.ensure_entry_for_existing_file(
            storage_key,
            safe_blob_file_name(extension),
            kind=StorageEntryKind.ATTACHMENT_BLOB,
            resource_id=attachment_key.resource_id,
            state=StorageEntryState.COMMITTED,
            protection=protection,
        )
        storage_index.upsert_blob_remote_map(
            blob_entry_id=entry.id or 0,
            fileobj=fileobj,
            ngw_aid=ngw_aid,
            sha256=entry.sha256,
            mime_type=None,
            original_name=Path(path).name,
        )
        storage_index.upsert_attachment_record(
            attachment_key,
            committed_blob_entry_id=entry.id,
            staged_blob_entry_id=None,
            active_blob_entry_id=entry.id,
            preview_entry_id=None,
            pending_operation=AttachmentOperation.NONE,
        )
        return entry

    def register_blob_file(
        self,
        attachment_key: AttachmentKey,
        storage_key: StorageKey,
        file_name: str,
        *,
        state: StorageEntryState,
        protection: StorageEntryProtection,
        pending_operation: AttachmentOperation,
        fileobj: Optional[object] = None,
        ngw_aid: Optional[int] = None,
        mime_type: Optional[str] = None,
        original_name: Optional[str] = None,
    ) -> Optional[StorageEntry]:
        """Register an existing attachment blob file."""
        path = self._path_resolver.resolve(storage_key, file_name)
        if not path.exists():
            return None

        storage_index = self._storage_index
        file_store = FileStore(self._path_resolver, storage_index)
        entry = file_store.ensure_entry_for_existing_file(
            storage_key,
            file_name,
            kind=StorageEntryKind.ATTACHMENT_BLOB,
            resource_id=attachment_key.resource_id,
            state=state,
            protection=protection,
        )
        record = storage_index.attachment_record(attachment_key)
        committed_blob_entry_id = self._record_entry_id(
            record,
            "committed_blob_entry_id",
        )
        staged_blob_entry_id = self._record_entry_id(
            record,
            "staged_blob_entry_id",
        )
        preview_entry_id = self._record_entry_id(record, "preview_entry_id")

        if state == StorageEntryState.STAGED:
            staged_blob_entry_id = entry.id
            active_blob_entry_id = entry.id
        else:
            committed_blob_entry_id = entry.id
            active_blob_entry_id = entry.id
            if state == StorageEntryState.COMMITTED:
                staged_blob_entry_id = None

        storage_index.upsert_attachment_record(
            attachment_key,
            committed_blob_entry_id=committed_blob_entry_id,
            staged_blob_entry_id=staged_blob_entry_id,
            active_blob_entry_id=active_blob_entry_id,
            preview_entry_id=preview_entry_id,
            pending_operation=pending_operation,
        )
        if fileobj is not None and entry.id is not None:
            storage_index.upsert_blob_remote_map(
                blob_entry_id=entry.id,
                fileobj=fileobj,
                ngw_aid=ngw_aid,
                sha256=entry.sha256,
                mime_type=mime_type,
                original_name=original_name,
            )
        return entry

    def register_preview_file(
        self,
        attachment_key: AttachmentKey,
        blob_storage_key: StorageKey,
        *,
        preview_profile: str = "default",
    ) -> Optional[StorageEntry]:
        """Register an existing attachment preview file."""
        storage_key = self.preview_key(blob_storage_key, preview_profile)
        path = self._path_resolver.resolve(storage_key, "preview.jpg")
        if not path.exists():
            return None

        storage_index = self._storage_index
        file_store = FileStore(self._path_resolver, storage_index)
        entry = file_store.ensure_entry_for_existing_file(
            storage_key,
            "preview.jpg",
            kind=StorageEntryKind.ATTACHMENT_PREVIEW,
            resource_id=attachment_key.resource_id,
            state=StorageEntryState.COMMITTED,
            protection=StorageEntryProtection.NONE,
        )
        record = storage_index.attachment_record(attachment_key)
        pending_operation = AttachmentOperation.NONE
        is_deleted_locally = False
        is_deleted_remotely = False
        if record is not None:
            pending_operation = AttachmentOperation(
                str(record["pending_operation"])
            )
            is_deleted_locally = bool(record["is_deleted_locally"])
            is_deleted_remotely = bool(record["is_deleted_remotely"])
        storage_index.upsert_attachment_record(
            attachment_key,
            committed_blob_entry_id=self._record_entry_id(
                record,
                "committed_blob_entry_id",
            ),
            staged_blob_entry_id=self._record_entry_id(
                record,
                "staged_blob_entry_id",
            ),
            active_blob_entry_id=self._record_entry_id(
                record,
                "active_blob_entry_id",
            ),
            preview_entry_id=entry.id,
            pending_operation=pending_operation,
            is_deleted_locally=is_deleted_locally,
            is_deleted_remotely=is_deleted_remotely,
        )
        return entry

    @property
    def storage_index(self) -> SqliteStorageIndex:
        """Return the global storage index."""
        return self._storage_index

    def _record_entry_id(
        self,
        record: Optional[dict],
        key: str,
    ) -> Optional[int]:
        """Return an integer entry id from an attachment record."""
        if record is None:
            return None

        value = record.get(key)
        if value is None:
            return None
        return int(value)

    def _mark_entry_orphaned(
        self,
        storage_index: SqliteStorageIndex,
        entry_id: Optional[int],
    ) -> None:
        """Make a superseded staged blob eligible for cleanup."""
        if entry_id is None:
            return

        entry = storage_index.find_entry_by_id(entry_id)
        superseded_states = {
            StorageEntryState.STAGED,
            StorageEntryState.UPLOADED_PENDING_COMMIT,
        }
        if entry is None or entry.state not in superseded_states:
            return

        storage_index.update_entry(
            replace(
                entry,
                state=StorageEntryState.ORPHANED,
                protection=StorageEntryProtection.NONE,
            )
        )

    def _remove_empty_parents(
        self,
        directory: Path,
    ) -> None:
        """Remove empty blob directories below the cache root."""
        cache_root = self._path_resolver.cache_root.resolve()
        directory = directory.resolve()
        try:
            directory.relative_to(cache_root)
        except ValueError:
            return

        while directory != cache_root:
            try:
                directory.rmdir()
            except OSError:
                return
            directory = directory.parent
