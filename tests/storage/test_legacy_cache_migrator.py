import sqlite3
from pathlib import Path

from nextgis_connect.features.synchronization.infrastructure.storage import (
    LegacyCacheMigrator,
    StorageCleanupService,
)
from nextgis_connect.features.synchronization.infrastructure.storage.detached_layer_store import (
    DetachedLayerStore,
)
from nextgis_connect.platform.storage.file_store import FileStore
from nextgis_connect.platform.storage.models import (
    LayerKey,
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
