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
        storage_index = self._attachment_store.index_for_instance(
            attachment_key.instance_uuid
        )
        previous_record = storage_index.attachment_record(attachment_key)
        previous_staged_entry_id = None
        if previous_record is not None:
            previous_staged_entry_id = previous_record["staged_blob_entry_id"]

        blob_ref = self._attachment_store.stage_blob(
            attachment_key,
            source_path,
            local_blob_uuid=local_blob_uuid,
            extension=extension,
            pending_operation=AttachmentOperation.UPDATE_FILE,
            committed_blob_entry_id=committed_blob_entry_id,
        )

        if previous_staged_entry_id is not None:
            previous_entry = storage_index.find_entry_by_id(
                int(previous_staged_entry_id)
            )
            if (
                previous_entry is not None
                and previous_entry.state == StorageEntryState.STAGED
            ):
                storage_index.update_entry(
                    StorageEntry(
                        id=previous_entry.id,
                        storage_key=previous_entry.storage_key,
                        kind=previous_entry.kind,
                        relative_path=previous_entry.relative_path,
                        instance_uuid=previous_entry.instance_uuid,
                        resource_id=previous_entry.resource_id,
                        size_bytes=previous_entry.size_bytes,
                        sha256=previous_entry.sha256,
                        state=StorageEntryState.ORPHANED,
                        protection=StorageEntryProtection.NONE,
                    )
                )

        return blob_ref

    def mark_uploaded_pending_commit(
        self,
        attachment_key: AttachmentKey,
        *,
        staged_blob_entry_id: int,
        fileobj: object,
        ngw_aid: Optional[int],
    ) -> None:
        """Mark a staged blob as uploaded but not server-committed."""
        storage_index = self._attachment_store.index_for_instance(
            attachment_key.instance_uuid
        )
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
