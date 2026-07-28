import hashlib
import os
import re
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import quote

from nextgis_connect.features.synchronization.infrastructure.storage.detached_layer_store import (
    DetachedLayerStore,
)
from nextgis_connect.features.synchronization.infrastructure.storage.qgis_project_storage_usage import (
    EmptyProjectStorageUsage,
    ProjectStorageUsage,
    normalize_used_paths,
)
from nextgis_connect.platform.storage.errors import StorageMigrationError
from nextgis_connect.platform.storage.migration_report import MigrationReport
from nextgis_connect.platform.storage.models import LayerKey


@dataclass(frozen=True)
class _LegacyContainerMetadata:
    """Represent legacy detached container metadata."""

    instance_uuid: Optional[str]
    resource_id: Optional[int]
    connection_id: Optional[str]
    has_local_changes: bool


@dataclass(frozen=True)
class _LegacyContainerCandidate:
    """Represent a legacy detached container candidate."""

    source_path: Path
    legacy_instance_uuid: str
    legacy_resource_id: Optional[int]


class LegacyCacheMigrator:
    """Migrate legacy detached storage into the indexed storage layout."""

    _UUID_PATTERN = re.compile(
        r"^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-"
        r"[89ab][a-f0-9]{3}-[a-f0-9]{12}$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        cache_root: Path,
        project_usage: Optional[ProjectStorageUsage] = None,
    ) -> None:
        """Initialize legacy cache migrator."""
        self._cache_root = Path(cache_root)
        self._layer_store = DetachedLayerStore(self._cache_root)
        self._project_usage = project_usage or EmptyProjectStorageUsage()

    def need_migration(self) -> bool:
        """Return whether legacy storage layout exists."""
        return any(True for _ in self._scan_candidates())

    def can_migrate(self) -> bool:
        """Return whether migration can run safely now."""
        used_paths = normalize_used_paths(self._project_usage.used_paths())
        for candidate in self._scan_candidates():
            try:
                if candidate.source_path.resolve() in used_paths:
                    return False
            except OSError:
                if candidate.source_path in used_paths:
                    return False
        return not self._lock_path.exists()

    def dry_run(self) -> MigrationReport:
        """Inspect migration actions without changing files."""
        return self._migrate(dry_run=True)

    def migrate(self) -> MigrationReport:
        """Migrate legacy storage layout into the current storage layout."""
        lock_descriptor = self._acquire_lock()
        try:
            return self._migrate(dry_run=False)
        finally:
            os.close(lock_descriptor)
            self._lock_path.unlink(missing_ok=True)

    @property
    def _lock_path(self) -> Path:
        """Return migration lock path."""
        return self._cache_root / ".storage_migration.lock"

    def _acquire_lock(self) -> int:
        """Acquire the migration lock."""
        self._cache_root.mkdir(parents=True, exist_ok=True)
        try:
            return os.open(
                str(self._lock_path),
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
            )
        except FileExistsError as error:
            raise StorageMigrationError(
                "Storage migration is already running",
                path=self._lock_path,
            ) from error

    def _migrate(self, *, dry_run: bool) -> MigrationReport:
        """Run migration or dry-run inspection."""
        report = MigrationReport()
        used_paths = normalize_used_paths(self._project_usage.used_paths())
        for candidate in self._scan_candidates():
            report.scanned_files += 1
            self._migrate_candidate(
                candidate,
                report,
                used_paths=used_paths,
                dry_run=dry_run,
            )
        return report

    def _migrate_candidate(
        self,
        candidate: _LegacyContainerCandidate,
        report: MigrationReport,
        *,
        used_paths: Iterable[Path],
        dry_run: bool,
    ) -> None:
        """Migrate one legacy container candidate."""
        metadata = self._read_metadata(candidate.source_path)
        if metadata is None:
            report.skipped_files += 1
            report.warnings.append(
                f"Legacy container is invalid and was left untouched: "
                f"{candidate.source_path}"
            )
            return

        instance_uuid = (
            metadata.instance_uuid or candidate.legacy_instance_uuid
        )
        resource_id = metadata.resource_id or candidate.legacy_resource_id
        if resource_id is None:
            report.skipped_files += 1
            report.warnings.append(
                "Could not determine resource id for legacy container: "
                f"{candidate.source_path}"
            )
            return

        layer_key = LayerKey(instance_uuid, resource_id)
        target_path = self._layer_store.container_path(layer_key)
        if dry_run:
            report.migrated_files += 1
            return

        if target_path.exists():
            self._handle_existing_target(
                candidate,
                target_path,
                report,
            )
            return

        try:
            entry = self._layer_store.ensure_container_entry(
                layer_key,
                candidate.source_path,
                connection_id=metadata.connection_id,
                has_local_changes=metadata.has_local_changes,
                is_used_by_project=self._is_used(
                    candidate.source_path, used_paths
                ),
            )
            if entry.id is None:
                raise StorageMigrationError(
                    "Migrated container has no index entry id",
                    path=target_path,
                )
            self._move_service_files(candidate.source_path, target_path)
        except Exception as error:
            report.errors.append(str(error))
            report.blocked_files += 1
            return

        if self._is_used(candidate.source_path, used_paths):
            report.blocked_files += 1
            report.warnings.append(
                "Migrated target was created, but legacy source is still used "
                f"by the current project: {candidate.source_path}"
            )
            return

        candidate.source_path.unlink(missing_ok=True)
        self._remove_empty_legacy_directories(candidate.source_path.parent)
        report.migrated_files += 1

    def _handle_existing_target(
        self,
        candidate: _LegacyContainerCandidate,
        target_path: Path,
        report: MigrationReport,
    ) -> None:
        """Handle migration when the target already exists."""
        if self._same_file(candidate.source_path, target_path):
            candidate.source_path.unlink(missing_ok=True)
            self._move_service_files(candidate.source_path, target_path)
            self._remove_empty_legacy_directories(candidate.source_path.parent)
            report.skipped_files += 1
            return

        report.blocked_files += 1
        report.errors.append(
            "Migration target already exists with different content: "
            f"{target_path}"
        )

    def _scan_candidates(self) -> Iterable[_LegacyContainerCandidate]:
        """Yield legacy detached container candidates."""
        if not self._cache_root.exists():
            return []

        candidates: List[_LegacyContainerCandidate] = []
        for instance_dir in self._cache_root.iterdir():
            if not instance_dir.is_dir():
                continue
            if not self._UUID_PATTERN.match(instance_dir.name):
                continue

            # Previous cache manager layout:
            # <cache_root>/<domain_uuid>/<resource_id>.gpkg
            for gpkg_path in instance_dir.glob("*.gpkg"):
                candidates.append(
                    _LegacyContainerCandidate(
                        source_path=gpkg_path,
                        legacy_instance_uuid=instance_dir.name,
                        legacy_resource_id=self._parse_int(gpkg_path.stem),
                    )
                )
        return candidates

    def _read_metadata(
        self,
        path: Path,
    ) -> Optional[_LegacyContainerMetadata]:
        """Read detached metadata without QGIS runtime."""
        try:
            database_uri = (
                f"file:{quote(str(path), safe='/')}?mode=ro&immutable=1"
            )
            with sqlite3.connect(database_uri, uri=True) as connection:
                cursor = connection.cursor()
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'ngw_metadata'
                    """
                )
                if int(cursor.fetchone()[0]) != 1:
                    return None

                columns = self._table_columns(cursor, "ngw_metadata")
                metadata = self._read_metadata_values(cursor, columns)
                has_local_changes = self._has_local_changes(cursor)
                return _LegacyContainerMetadata(
                    instance_uuid=metadata.get("instance_id"),
                    resource_id=self._parse_int(metadata.get("resource_id")),
                    connection_id=metadata.get("connection_id"),
                    has_local_changes=has_local_changes,
                )
        except sqlite3.DatabaseError:
            return None

    def _read_metadata_values(
        self,
        cursor: sqlite3.Cursor,
        columns: List[str],
    ) -> dict:
        """Read selected ngw_metadata values."""
        selected_columns = [
            column
            for column in ("instance_id", "resource_id", "connection_id")
            if column in columns
        ]
        if not selected_columns:
            return {}

        cursor.execute(
            f"SELECT {', '.join(selected_columns)} FROM ngw_metadata LIMIT 1"
        )
        row = cursor.fetchone()
        if row is None:
            return {}
        return dict(zip(selected_columns, row))

    def _table_columns(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
    ) -> List[str]:
        """Return table column names."""
        cursor.execute(f"PRAGMA table_info({table_name})")
        return [str(row[1]) for row in cursor.fetchall()]

    def _has_local_changes(self, cursor: sqlite3.Cursor) -> bool:
        """Return whether a detached container has local changes."""
        change_tables = (
            "ngw_created_features",
            "ngw_deleted_features",
            "ngw_updated_attributes",
            "ngw_features_with_updated_geometries",
            "ngw_added_features_attachments",
            "ngw_updated_features_attachments",
            "ngw_removed_features_attachments",
        )
        for table_name in change_tables:
            if not self._table_exists(cursor, table_name):
                continue
            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
            if int(cursor.fetchone()[0]) > 0:
                return True
        return False

    def _table_exists(
        self,
        cursor: sqlite3.Cursor,
        table_name: str,
    ) -> bool:
        """Return whether a table exists."""
        cursor.execute(
            """
            SELECT COUNT(*)
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (table_name,),
        )
        return int(cursor.fetchone()[0]) == 1

    def _move_service_files(
        self,
        source_path: Path,
        target_path: Path,
    ) -> None:
        """Move legacy GeoPackage service files next to the target."""
        for service_file in source_path.parent.glob(f"{source_path.name}-*"):
            suffix = service_file.name[len(source_path.name) :]
            target_file = target_path.parent / f"{target_path.name}{suffix}"
            if target_file.exists():
                continue
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(service_file), str(target_file))

    def _remove_empty_legacy_directories(self, start_directory: Path) -> None:
        """Remove empty legacy directories below cache root."""
        current_directory = start_directory
        while current_directory != self._cache_root:
            try:
                current_directory.rmdir()
            except OSError:
                return
            current_directory = current_directory.parent

    def _same_file(self, first_path: Path, second_path: Path) -> bool:
        """Return whether two files have the same digest."""
        if not first_path.exists() or not second_path.exists():
            return False
        return self._sha256(first_path) == self._sha256(second_path)

    def _sha256(self, path: Path) -> str:
        """Return SHA-256 digest for a file."""
        digest = hashlib.sha256()
        with path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _is_used(self, path: Path, used_paths: Iterable[Path]) -> bool:
        """Return whether a path is used by the current project."""
        try:
            resolved_path = path.resolve()
        except OSError:
            resolved_path = path
        return resolved_path in used_paths

    def _parse_int(self, value: object) -> Optional[int]:
        """Parse an integer value."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
