import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from nextgis_connect.platform.storage.file_store import FileStore
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    StorageEntry,
    StorageEntryKind,
    StorageEntryProtection,
    StorageEntryState,
)
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)
from nextgis_connect.platform.storage.storage_key import StorageKeyFactory


def test_schema_creation(tmp_path: Path) -> None:
    index_path = tmp_path / "instance" / "storage.sqlite"
    storage_index = SqliteStorageIndex(index_path)

    storage_index.initialize()

    with sqlite3.connect(str(index_path)) as connection:
        cursor = connection.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            """
        )
        tables = {row[0] for row in cursor.fetchall()}

    assert {
        "storage_schema",
        "storage_entries",
        "layer_entries",
        "attachment_records",
        "blob_remote_map",
        "storage_leases",
    }.issubset(tables)


def test_add_find_update_storage_entry(tmp_path: Path) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    storage_key = StorageKeyFactory.remote_attachment_blob(
        instance_uuid,
        42,
        100,
    )
    storage_index = SqliteStorageIndex(
        tmp_path / instance_uuid / "storage.sqlite"
    )
    entry = StorageEntry(
        id=None,
        storage_key=storage_key,
        kind=StorageEntryKind.ATTACHMENT_BLOB,
        relative_path=Path(storage_key.digest[:2], storage_key.digest, "blob"),
        instance_uuid=instance_uuid,
        resource_id=42,
        size_bytes=10,
        sha256="a",
        state=StorageEntryState.COMMITTED,
        protection=StorageEntryProtection.NONE,
    )

    stored_entry = storage_index.add_entry(entry)
    updated_entry = StorageEntry(
        id=stored_entry.id,
        storage_key=stored_entry.storage_key,
        kind=stored_entry.kind,
        relative_path=stored_entry.relative_path,
        instance_uuid=stored_entry.instance_uuid,
        resource_id=stored_entry.resource_id,
        size_bytes=20,
        sha256="b",
        state=StorageEntryState.ORPHANED,
        protection=StorageEntryProtection.NONE,
    )
    storage_index.update_entry(updated_entry)

    found_entry = storage_index.find_entry(storage_key)

    assert found_entry is not None
    assert found_entry.id == stored_entry.id
    assert found_entry.size_bytes == 20
    assert found_entry.state == StorageEntryState.ORPHANED


def test_lease_blocks_gc_until_release(tmp_path: Path) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    storage_index = SqliteStorageIndex(
        tmp_path / instance_uuid / "storage.sqlite"
    )
    entry = _write_entry(tmp_path, storage_index, instance_uuid)
    assert entry.id is not None

    storage_index.acquire_lease(
        entry.id,
        "test",
        "operation-1",
        datetime.now(timezone.utc) + timedelta(hours=1),
    )

    assert storage_index.gc_candidates() == []

    storage_index.release_lease("operation-1")

    assert storage_index.gc_candidates() == [entry]


def test_gc_skips_protected_and_uploaded_entries(tmp_path: Path) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    storage_index = SqliteStorageIndex(
        tmp_path / instance_uuid / "storage.sqlite"
    )
    dirty_entry = _write_entry(
        tmp_path,
        storage_index,
        instance_uuid,
        suffix="dirty",
        protection=StorageEntryProtection.DIRTY,
    )
    uploaded_entry = _write_entry(
        tmp_path,
        storage_index,
        instance_uuid,
        suffix="uploaded",
        state=StorageEntryState.UPLOADED_PENDING_COMMIT,
    )
    rollback_entry = _write_entry(
        tmp_path,
        storage_index,
        instance_uuid,
        suffix="rollback",
        protection=StorageEntryProtection.RETAIN_FOR_ROLLBACK,
    )

    candidates = storage_index.gc_candidates()

    assert dirty_entry not in candidates
    assert uploaded_entry not in candidates
    assert rollback_entry not in candidates


def test_gc_skips_blob_referenced_by_pending_delete(tmp_path: Path) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    storage_index = SqliteStorageIndex(
        tmp_path / instance_uuid / "storage.sqlite"
    )
    blob_entry = _write_entry(tmp_path, storage_index, instance_uuid)
    assert blob_entry.id is not None
    storage_index.upsert_attachment_record(
        AttachmentKey(
            instance_uuid=instance_uuid,
            resource_id=42,
            feature_local_id=1,
            feature_ngw_fid=None,
            local_attachment_id=None,
            ngw_aid=100,
        ),
        committed_blob_entry_id=blob_entry.id,
        staged_blob_entry_id=None,
        active_blob_entry_id=blob_entry.id,
        preview_entry_id=None,
        pending_operation=AttachmentOperation.DELETE,
    )

    assert storage_index.gc_candidates() == []


def test_gc_skips_referenced_attachment_by_default(tmp_path: Path) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    storage_index = SqliteStorageIndex(
        tmp_path / instance_uuid / "storage.sqlite"
    )
    blob_entry = _write_entry(tmp_path, storage_index, instance_uuid)
    assert blob_entry.id is not None
    storage_index.upsert_attachment_record(
        AttachmentKey(
            instance_uuid=instance_uuid,
            resource_id=42,
            feature_local_id=1,
            feature_ngw_fid=101,
            local_attachment_id="100",
            ngw_aid=100,
        ),
        committed_blob_entry_id=blob_entry.id,
        staged_blob_entry_id=None,
        active_blob_entry_id=blob_entry.id,
        preview_entry_id=None,
        pending_operation=AttachmentOperation.NONE,
    )

    assert storage_index.gc_candidates() == []


def test_gc_includes_referenced_attachment_when_requested(
    tmp_path: Path,
) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    storage_index = SqliteStorageIndex(
        tmp_path / instance_uuid / "storage.sqlite"
    )
    blob_entry = _write_entry(tmp_path, storage_index, instance_uuid)
    assert blob_entry.id is not None
    storage_index.upsert_attachment_record(
        AttachmentKey(
            instance_uuid=instance_uuid,
            resource_id=42,
            feature_local_id=1,
            feature_ngw_fid=101,
            local_attachment_id="100",
            ngw_aid=100,
        ),
        committed_blob_entry_id=blob_entry.id,
        staged_blob_entry_id=None,
        active_blob_entry_id=blob_entry.id,
        preview_entry_id=None,
        pending_operation=AttachmentOperation.NONE,
    )

    candidates = storage_index.gc_candidates(
        delete_referenced_attachments=True
    )

    assert candidates == [blob_entry]


def _write_entry(
    tmp_path: Path,
    storage_index: SqliteStorageIndex,
    instance_uuid: str,
    *,
    suffix: str = "default",
    state: StorageEntryState = StorageEntryState.COMMITTED,
    protection: StorageEntryProtection = StorageEntryProtection.NONE,
) -> StorageEntry:
    storage_key = StorageKeyFactory.remote_attachment_blob(
        instance_uuid,
        42,
        suffix,
    )
    path_resolver = StoragePathResolver(tmp_path)
    file_store = FileStore(path_resolver, storage_index)
    blob_ref = file_store.write_bytes(
        storage_key,
        "blob",
        f"payload-{suffix}".encode(),
        kind=StorageEntryKind.ATTACHMENT_BLOB,
        resource_id=42,
        state=state,
        protection=protection,
    )
    assert blob_ref.entry_id is not None
    entry = storage_index.find_entry_by_id(blob_ref.entry_id)
    assert entry is not None
    return entry
