import uuid
from pathlib import Path
from typing import Dict, Optional

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
        self._indexes: Dict[str, SqliteStorageIndex] = {}

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
        blob_uuid = local_blob_uuid or str(uuid.uuid4())
        storage_key = self.local_blob_key(
            attachment_key.instance_uuid,
            attachment_key.resource_id,
            blob_uuid,
        )
        storage_index = self._index_for_instance(attachment_key.instance_uuid)
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
        return blob_ref

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
        storage_index = self._index_for_instance(attachment_key.instance_uuid)
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

        storage_index = self._index_for_instance(attachment_key.instance_uuid)
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

        storage_index = self._index_for_instance(attachment_key.instance_uuid)
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
            pending_operation=AttachmentOperation.NONE,
        )
        return entry

    def index_for_instance(self, instance_uuid: str) -> SqliteStorageIndex:
        """Return storage index for an instance."""
        return self._index_for_instance(instance_uuid)

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

    def _index_for_instance(self, instance_uuid: str) -> SqliteStorageIndex:
        """Return index for an instance."""
        storage_index = self._indexes.get(instance_uuid)
        if storage_index is not None:
            return storage_index

        storage_index = SqliteStorageIndex(
            self._path_resolver.index_path(instance_uuid)
        )
        storage_index.initialize()
        self._indexes[instance_uuid] = storage_index
        return storage_index
