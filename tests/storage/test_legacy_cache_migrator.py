import os
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Tuple
from unittest.mock import Mock

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
    index_path = tmp_path / "storage.sqlite"
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


def test_migration_deletes_previous_hashed_beta_layout(
    tmp_path: Path,
) -> None:
    legacy_digest = "a" * 64
    source_path = (
        tmp_path
        / INSTANCE_UUID
        / legacy_digest[:2]
        / legacy_digest
        / "42.gpkg"
    )
    _create_container(source_path, INSTANCE_UUID, 42)

    report = LegacyCacheMigrator(tmp_path).migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert report.migrated_files == 0
    assert report.deleted_files == 1
    assert not source_path.exists()
    assert not target_path.exists()


def test_migration_deletes_indexed_beta_cache_files(
    tmp_path: Path,
) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    SqliteStorageIndex(beta_directory / "storage.sqlite").initialize()
    digest = "b" * 64
    blob_path = beta_directory / digest[:2] / digest / "blob"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"large beta cache")

    migrator = LegacyCacheMigrator(tmp_path)
    assert migrator.need_migration()

    report = migrator.migrate()

    assert report.deleted_files >= 2
    assert not blob_path.exists()
    assert not (beta_directory / "storage.sqlite").exists()
    assert not beta_directory.exists()
    assert not migrator.need_migration()


def test_migration_deletes_root_beta_index_cache(
    tmp_path: Path,
) -> None:
    _create_beta_schema_index(tmp_path / "storage.sqlite")
    digest = "a" * 64
    blob_path = tmp_path / digest[:2] / digest / "blob"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"root beta cache")

    migrator = LegacyCacheMigrator(tmp_path)
    assert migrator.need_migration()

    report = migrator.migrate()

    assert report.blocked_files == 0
    assert report.deleted_files >= 2
    assert tmp_path.exists()
    assert not blob_path.exists()
    assert not (tmp_path / "storage.sqlite").exists()
    assert not migrator.need_migration()


def test_current_root_index_does_not_require_migration(
    tmp_path: Path,
) -> None:
    SqliteStorageIndex(tmp_path / "storage.sqlite").initialize()
    digest = "b" * StoragePathResolver.DIGEST_DIRECTORY_LENGTH
    blob_path = tmp_path / digest[:2] / digest / "blob"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"current cache")

    migrator = LegacyCacheMigrator(tmp_path)

    assert not migrator.need_migration()
    assert blob_path.exists()


def test_migration_deletes_beta_cache_when_index_is_corrupted(
    tmp_path: Path,
) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    index_path = beta_directory / "storage.sqlite"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_bytes(b"not a sqlite database")
    digest = "f" * 64
    blob_path = beta_directory / digest[:2] / digest / "blob"
    blob_path.parent.mkdir(parents=True, exist_ok=True)
    blob_path.write_bytes(b"possibly irreplaceable")

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.blocked_files == 0
    assert not index_path.exists()
    assert not blob_path.exists()


def test_migration_deletes_unreadable_dirty_beta_container(
    tmp_path: Path,
) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    storage_index = SqliteStorageIndex(beta_directory / "storage.sqlite")
    layer_key = LayerKey(INSTANCE_UUID, 42)
    storage_key = StorageKeyFactory.layer_container(layer_key)
    relative_path = Path(
        storage_key.digest[:2],
        storage_key.digest,
        "42.gpkg",
    )
    source_path = beta_directory / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"corrupted local container")
    stored_entry = storage_index.add_entry(
        StorageEntry(
            id=None,
            storage_key=storage_key,
            kind=StorageEntryKind.LAYER_CONTAINER,
            relative_path=relative_path,
            instance_uuid=INSTANCE_UUID,
            resource_id=42,
            size_bytes=source_path.stat().st_size,
            sha256=None,
            state=StorageEntryState.COMMITTED,
            protection=StorageEntryProtection.DIRTY,
        )
    )
    assert stored_entry.id is not None
    storage_index.upsert_layer_entry(
        resource_id=42,
        container_entry_id=stored_entry.id,
        connection_id="connection",
        instance_uuid=INSTANCE_UUID,
        has_local_changes=True,
        is_used_by_project=False,
        last_sync_state=None,
    )

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.blocked_files == 0
    assert not source_path.exists()
    assert not (beta_directory / "storage.sqlite").exists()


def test_migration_deletes_clean_beta_container(tmp_path: Path) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    SqliteStorageIndex(beta_directory / "storage.sqlite").initialize()
    digest = "c" * 64
    source_path = beta_directory / digest[:2] / digest / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)

    report = LegacyCacheMigrator(tmp_path).migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert report.deleted_files >= 2
    assert not source_path.exists()
    assert not target_path.exists()


def test_migration_deletes_unsynchronized_beta_attachment(
    tmp_path: Path,
) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    attachment_key, source_path = _write_beta_staged_attachment(beta_directory)

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.errors == []
    assert report.migrated_files == 0
    assert not source_path.exists()
    assert not beta_directory.exists()
    assert not (tmp_path / "storage.sqlite").exists()
    storage_index = SqliteStorageIndex(tmp_path / "storage.sqlite")
    assert storage_index.attachment_record(attachment_key) is None


def test_migration_deletes_dirty_beta_container(tmp_path: Path) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    SqliteStorageIndex(beta_directory / "storage.sqlite").initialize()
    digest = "d" * 64
    source_path = beta_directory / digest[:2] / digest / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42, has_changes=True)

    report = LegacyCacheMigrator(tmp_path).migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert report.migrated_files == 0
    assert not source_path.exists()
    assert not target_path.exists()


def test_migration_deletes_beta_container_used_by_project(
    tmp_path: Path,
) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    SqliteStorageIndex(beta_directory / "storage.sqlite").initialize()
    digest = "e" * 64
    source_path = beta_directory / digest[:2] / digest / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    project_usage = Mock()
    project_usage.used_paths.return_value = {source_path}
    migrator = LegacyCacheMigrator(tmp_path, project_usage)

    assert migrator.can_migrate()

    report = migrator.migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert report.blocked_files == 0
    assert not source_path.exists()
    assert not target_path.exists()
    assert not (beta_directory / "storage.sqlite").exists()


def test_migration_keeps_flat_container_next_to_beta_cache(
    tmp_path: Path,
) -> None:
    beta_directory = tmp_path / INSTANCE_UUID
    flat_source_path = beta_directory / "42.gpkg"
    _create_container(flat_source_path, INSTANCE_UUID, 42)
    SqliteStorageIndex(beta_directory / "storage.sqlite").initialize()
    digest = "f" * 64
    beta_blob_path = beta_directory / digest[:2] / digest / "blob"
    beta_blob_path.parent.mkdir(parents=True, exist_ok=True)
    beta_blob_path.write_bytes(b"beta")

    report = LegacyCacheMigrator(tmp_path).migrate()

    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert report.migrated_files == 1
    assert target_path.exists()
    assert not flat_source_path.exists()
    assert not beta_blob_path.exists()
    assert not (beta_directory / "storage.sqlite").exists()


def test_migrates_legacy_cache_to_another_root(tmp_path: Path) -> None:
    source_root = tmp_path / "old"
    target_root = tmp_path / "new"
    source_path = source_root / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)

    report = LegacyCacheMigrator(
        source_root,
        target_cache_root=target_root,
    ).migrate()

    target_path = DetachedLayerStore(target_root).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    assert report.migrated_files == 1
    assert not source_path.exists()
    assert target_path.exists()


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


def test_migration_keeps_used_source_when_same_target_exists(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(source_path.read_bytes())
    project_usage = Mock()
    project_usage.used_paths.return_value = {source_path}

    report = LegacyCacheMigrator(tmp_path, project_usage).migrate()

    assert report.blocked_files == 1
    assert source_path.exists()
    assert target_path.exists()


def test_migration_registers_existing_matching_target(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    layer_store = DetachedLayerStore(tmp_path)
    target_path = layer_store.container_path(LayerKey(INSTANCE_UUID, 42))
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(source_path.read_bytes())

    report = LegacyCacheMigrator(tmp_path).migrate()

    storage_index = SqliteStorageIndex(tmp_path / "storage.sqlite")
    layer_entry = storage_index.layer_entry(LayerKey(INSTANCE_UUID, 42))
    assert report.errors == []
    assert not source_path.exists()
    assert layer_entry is not None


def test_migration_keeps_source_on_service_file_conflict(
    tmp_path: Path,
) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    _create_container(source_path, INSTANCE_UUID, 42)
    source_service_path = source_path.parent / "42.gpkg-wal"
    source_service_path.write_text("source", encoding="utf-8")
    target_path = DetachedLayerStore(tmp_path).container_path(
        LayerKey(INSTANCE_UUID, 42)
    )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_bytes(source_path.read_bytes())
    target_service_path = target_path.parent / f"{target_path.name}-wal"
    target_service_path.write_text("target", encoding="utf-8")

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.blocked_files == 1
    assert source_path.exists()
    assert source_service_path.read_text(encoding="utf-8") == "source"
    assert target_service_path.read_text(encoding="utf-8") == "target"


def test_migration_leaves_invalid_gpkg_untouched(tmp_path: Path) -> None:
    source_path = tmp_path / INSTANCE_UUID / "42.gpkg"
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_text("not sqlite", encoding="utf-8")

    report = LegacyCacheMigrator(tmp_path).migrate()

    assert report.skipped_files == 1
    assert source_path.exists()


def test_cleanup_deletes_previews_before_blobs(tmp_path: Path) -> None:
    storage_index = SqliteStorageIndex(tmp_path / "storage.sqlite")
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

    storage_index = attachment_cache.attachment_store.storage_index
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
    storage_index = SqliteStorageIndex(tmp_path / "storage.sqlite")
    entry = _write_disposable_entry(tmp_path, storage_index, "old")
    path = StoragePathResolver(tmp_path).absolute_from_entry(
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
    storage_index = SqliteStorageIndex(tmp_path / "storage.sqlite")
    first_entry = _write_disposable_entry(tmp_path, storage_index, "first")
    second_entry = _write_disposable_entry(tmp_path, storage_index, "second")
    path_resolver = StoragePathResolver(tmp_path)
    first_path = path_resolver.absolute_from_entry(
        first_entry.relative_path,
    )
    second_path = path_resolver.absolute_from_entry(
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


def _write_beta_staged_attachment(
    beta_directory: Path,
) -> Tuple[AttachmentKey, Path]:
    storage_index = SqliteStorageIndex(beta_directory / "storage.sqlite")
    storage_key = StorageKeyFactory.local_attachment_blob(
        INSTANCE_UUID,
        42,
        "beta-staged-attachment",
    )
    relative_path = Path(
        storage_key.digest[:2],
        storage_key.digest,
        "blob.bin",
    )
    source_path = beta_directory / relative_path
    source_path.parent.mkdir(parents=True, exist_ok=True)
    source_path.write_bytes(b"unsynchronized attachment")
    stored_entry = storage_index.add_entry(
        StorageEntry(
            id=None,
            storage_key=storage_key,
            kind=StorageEntryKind.ATTACHMENT_BLOB,
            relative_path=relative_path,
            instance_uuid=INSTANCE_UUID,
            resource_id=42,
            size_bytes=source_path.stat().st_size,
            sha256=None,
            state=StorageEntryState.UPLOADED_PENDING_COMMIT,
            protection=StorageEntryProtection.DIRTY,
        )
    )
    assert stored_entry.id is not None
    attachment_key = AttachmentKey(
        instance_uuid=INSTANCE_UUID,
        resource_id=42,
        feature_local_id=1,
        feature_ngw_fid=None,
        local_attachment_id="beta-attachment",
        ngw_aid=None,
    )
    storage_index.upsert_attachment_record(
        attachment_key,
        committed_blob_entry_id=None,
        staged_blob_entry_id=stored_entry.id,
        active_blob_entry_id=stored_entry.id,
        preview_entry_id=None,
        pending_operation=AttachmentOperation.CREATE,
    )
    storage_index.upsert_blob_remote_map(
        blob_entry_id=stored_entry.id,
        fileobj=777,
        ngw_aid=None,
        sha256=None,
        mime_type="application/octet-stream",
        original_name="attachment.bin",
    )
    return attachment_key, source_path


def _create_beta_schema_index(index_path: Path) -> None:
    """Create an index from a disposable beta storage schema."""
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(index_path)) as connection:
        connection.execute(
            """
            CREATE TABLE storage_schema (
                version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO storage_schema (version, created_at, updated_at)
            VALUES (
                2,
                '2026-08-01T00:00:00+00:00',
                '2026-08-01T00:00:00+00:00'
            )
            """
        )


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
