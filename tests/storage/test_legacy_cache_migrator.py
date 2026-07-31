import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from nextgis_connect.features.synchronization.infrastructure.storage import (
    AttachmentStore,
    LegacyCacheMigrator,
    StorageCleanupService,
)
from nextgis_connect.features.synchronization.infrastructure.storage.detached_layer_store import (
    DetachedLayerStore,
)
from nextgis_connect.platform.storage.file_store import FileStore
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    LayerKey,
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

INSTANCE_UUID = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"


@dataclass(frozen=True)
class _RegisteredAttachmentCache:
    attachment_store: AttachmentStore
    attachment_key: AttachmentKey
    blob_path: Path
    preview_path: Path


def test_migrates_resource_gpkg_to_indexed_layer_container(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)

    report = LegacyCacheMigrator(tmp_path).migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    index_path = tmp_path / INSTANCE_UUID / "storage.sqlite"
    assert report.migrated_files == 1
    assert not source_path.exists()
    assert target_path.exists()
    assert index_path.exists()


def test_migration_moves_service_files(tmp_path: Path) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    service_path = source_path.parent / "42.gpkg-wal"
    service_path.write_text("wal", encoding="utf-8")

    LegacyCacheMigrator(tmp_path).migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert not service_path.exists()
    assert (target_path.parent / f"{target_path.name}-wal").read_text(
        encoding="utf-8"
    ) == "wal"


def test_migration_is_idempotent(tmp_path: Path) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    migrator = LegacyCacheMigrator(tmp_path)

    first_report = migrator.migrate()
    second_report = migrator.migrate()

    assert first_report.migrated_files == 1
    assert second_report.scanned_files == 0
    assert second_report.errors == []


def test_migration_does_not_overwrite_existing_target_conflict(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text("different", encoding="utf-8")

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.blocked_files == 1
    assert source_path.exists()
    assert target_path.read_text(encoding="utf-8") == "different"


def test_migration_leaves_invalid_gpkg_untouched(tmp_path: Path) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("not sqlite", encoding="utf-8")

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.skipped_files == 1
    assert source_path.exists()


def test_cleanup_deletes_previews_before_blobs(tmp_path: Path) -> None:
    storage_index = SqliteStorageIndex(
        tmp_path / INSTANCE_UUID / "storage.sqlite"
    )
    path_resolver = StoragePathResolver(tmp_path)
    file_store = FileStore(path_resolver, storage_index)
    blob_key = StorageKeyFactory.remote_attachment_blob(INSTANCE_UUID, 42, 1)
    preview_key = StorageKeyFactory.attachment_preview(blob_key, "default")
    file_store.write_bytes(
        blob_key,
        "blob",
        b"blob",
        kind=StorageEntryKind.ATTACHMENT_BLOB,
        resource_id=42,
        state=StorageEntryState.COMMITTED,
        protection=StorageEntryProtection.NONE,
    )
    file_store.write_bytes(
        preview_key,
        "preview.jpg",
        b"preview",
        kind=StorageEntryKind.ATTACHMENT_PREVIEW,
        resource_id=42,
        state=StorageEntryState.COMMITTED,
        protection=StorageEntryProtection.NONE,
    )

    report = StorageCleanupService(tmp_path).clear_connection_cache(
        INSTANCE_UUID
    )

    assert [path.name for path in report.deleted_paths] == [
        "preview.jpg",
        "blob",
    ]


def test_cleanup_keeps_registered_remote_attachments_by_default(
    tmp_path: Path,
) -> None:
    attachment_cache = _write_registered_remote_attachment(tmp_path)

    report = StorageCleanupService(tmp_path).clear_disposable_cache()

    storage_index = attachment_cache.attachment_store.index_for_instance(
        INSTANCE_UUID
    )
    record = storage_index.attachment_record(attachment_cache.attachment_key)

    assert report.deleted_paths == []
    assert attachment_cache.blob_path.exists()
    assert attachment_cache.preview_path.exists()
    assert record is not None
    assert record["committed_blob_entry_id"] is not None
    assert record["active_blob_entry_id"] is not None
    assert record["preview_entry_id"] is not None


def test_automatic_purge_deletes_old_disposable_entry(
    tmp_path: Path,
) -> None:
    storage_index = SqliteStorageIndex(
        tmp_path / INSTANCE_UUID / "storage.sqlite"
    )
    entry = _write_disposable_entry(tmp_path, storage_index, "old")
    path = StoragePathResolver(tmp_path).absolute_from_entry(
        entry.instance_uuid,
        entry.relative_path,
    )
    old_time = time.time() - 2 * 24 * 60 * 60
    os.utime(path, (old_time, old_time))

    report = StorageCleanupService(tmp_path).purge_automatic(
        max_size_bytes=None,
        max_age_days=1,
    )

    assert report.deleted_files == 1
    assert not path.exists()


def test_automatic_purge_deletes_oldest_entries_until_under_size(
    tmp_path: Path,
) -> None:
    storage_index = SqliteStorageIndex(
        tmp_path / INSTANCE_UUID / "storage.sqlite"
    )
    first_entry = _write_disposable_entry(tmp_path, storage_index, "first")
    second_entry = _write_disposable_entry(tmp_path, storage_index, "second")
    path_resolver = StoragePathResolver(tmp_path)
    first_path = path_resolver.absolute_from_entry(
        first_entry.instance_uuid,
        first_entry.relative_path,
    )
    second_path = path_resolver.absolute_from_entry(
        second_entry.instance_uuid,
        second_entry.relative_path,
    )
    old_time = time.time() - 20
    new_time = time.time() - 10
    os.utime(first_path, (old_time, old_time))
    os.utime(second_path, (new_time, new_time))

    report = StorageCleanupService(tmp_path).purge_automatic(
        max_size_bytes=second_path.stat().st_size,
        max_age_days=None,
    )

    assert report.deleted_files == 1
    assert not first_path.exists()
    assert second_path.exists()


def test_clear_connection_cache_deletes_registered_remote_attachments(
    tmp_path: Path,
) -> None:
    attachment_cache = _write_registered_remote_attachment(tmp_path)

    report = StorageCleanupService(tmp_path).clear_connection_cache(
        INSTANCE_UUID
    )

    assert [path.name for path in report.deleted_paths] == [
        "preview.jpg",
        "blob",
    ]
    assert not attachment_cache.blob_path.exists()
    assert not attachment_cache.preview_path.exists()


def test_clear_resource_cache_deletes_resource_entries(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    layer_store = DetachedLayerStore(tmp_path)
    layer_store.ensure_container_entry(
        LayerKey(INSTANCE_UUID, 42), source_path
    )
    layer_path = layer_store.container_path(LayerKey(INSTANCE_UUID, 42))
    attachment_cache = _write_registered_remote_attachment(tmp_path)

    report = StorageCleanupService(tmp_path).clear_resource_cache(
        INSTANCE_UUID,
        42,
    )

    assert [path.name for path in report.deleted_paths] == [
        "preview.jpg",
        "blob",
        "42.gpkg",
    ]
    assert not layer_path.exists()
    assert not attachment_cache.blob_path.exists()
    assert not attachment_cache.preview_path.exists()


def test_clear_resource_cache_keeps_dirty_resource(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42, has_changes=True)
    layer_store = DetachedLayerStore(tmp_path)
    layer_store.ensure_container_entry(
        LayerKey(INSTANCE_UUID, 42),
        source_path,
        has_local_changes=True,
    )
    target_path = layer_store.container_path(LayerKey(INSTANCE_UUID, 42))

    report = StorageCleanupService(tmp_path).clear_resource_cache(
        INSTANCE_UUID,
        42,
    )

    assert report.blocked_files == 1
    assert target_path.exists()


def test_cleanup_does_not_delete_dirty_detached_container(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / "source.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42, has_changes=True)
    layer_store = DetachedLayerStore(tmp_path)
    layer_store.ensure_container_entry(
        LayerKey(INSTANCE_UUID, 42),
        source_path,
        has_local_changes=True,
    )
    target_path = layer_store.container_path(LayerKey(INSTANCE_UUID, 42))

    report = StorageCleanupService(tmp_path).clear_connection_cache(
        INSTANCE_UUID
    )

    assert report.blocked_files == 1
    assert target_path.exists()


def test_clear_connection_cache_allows_dirty_discard(tmp_path: Path) -> None:
    source_path = tmp_path / "source.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42, has_changes=True)
    layer_store = DetachedLayerStore(tmp_path)
    layer_store.ensure_container_entry(
        LayerKey(INSTANCE_UUID, 42),
        source_path,
        has_local_changes=True,
    )
    target_path = layer_store.container_path(LayerKey(INSTANCE_UUID, 42))

    report = StorageCleanupService(tmp_path).clear_connection_cache(
        INSTANCE_UUID,
        discard_dirty=True,
    )

    assert report.deleted_files == 1
    assert not target_path.exists()


def _write_registered_remote_attachment(
    tmp_path: Path,
) -> _RegisteredAttachmentCache:
    attachment_store = AttachmentStore(tmp_path)
    attachment_key = AttachmentKey(
        instance_uuid=INSTANCE_UUID,
        resource_id=42,
        feature_local_id=1,
        feature_ngw_fid=101,
        local_attachment_id="1",
        ngw_aid=1,
    )
    blob_key = StorageKeyFactory.remote_attachment_blob(
        INSTANCE_UUID,
        42,
        501,
    )
    blob_path = attachment_store.blob_path(blob_key)
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"blob")
    preview_path = attachment_store.preview_path(blob_key)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"preview")

    attachment_store.register_blob_file(
        attachment_key,
        blob_key,
        "blob",
        state=StorageEntryState.COMMITTED,
        protection=StorageEntryProtection.NONE,
        pending_operation=AttachmentOperation.NONE,
        fileobj=501,
        ngw_aid=1,
    )
    attachment_store.register_preview_file(
        attachment_key,
        blob_key,
    )
    return _RegisteredAttachmentCache(
        attachment_store=attachment_store,
        attachment_key=attachment_key,
        blob_path=blob_path,
        preview_path=preview_path,
    )


def _write_disposable_entry(
    tmp_path: Path,
    storage_index: SqliteStorageIndex,
    suffix: str,
) -> StorageEntry:
    path_resolver = StoragePathResolver(tmp_path)
    file_store = FileStore(path_resolver, storage_index)
    storage_key = StorageKeyFactory.temporary_file(
        INSTANCE_UUID,
        suffix,
        "test",
    )
    blob_ref = file_store.write_bytes(
        storage_key,
        f"{suffix}.tmp",
        f"payload-{suffix}".encode(),
        kind=StorageEntryKind.TEMPORARY_FILE,
        resource_id=None,
        state=StorageEntryState.TEMPORARY,
        protection=StorageEntryProtection.NONE,
    )
    assert blob_ref.entry_id is not None
    entry = storage_index.find_entry_by_id(blob_ref.entry_id)
    assert entry is not None
    return entry


def _create_container(
    path: Path,
    instance_uuid: str,
    resource_id: int,
    *,
    connection_id: str = "connection",
    has_changes: bool = False,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(path)) as connection:
        connection.execute(
            """
            CREATE TABLE ngw_metadata (
                instance_id TEXT,
                resource_id INTEGER,
                connection_id TEXT
            )
            """
        )
        connection.execute(
            """
            INSERT INTO ngw_metadata (
                instance_id,
                resource_id,
                connection_id
            )
            VALUES (?, ?, ?)
            """,
            (instance_uuid, resource_id, connection_id),
        )
        if has_changes:
            connection.execute(
                "CREATE TABLE ngw_updated_attributes (fid INTEGER)"
            )
            connection.execute(
                "INSERT INTO ngw_updated_attributes (fid) VALUES (1)"
            )
        connection.commit()
