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
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.storage_index_schema import (
    SCHEMA_VERSION,
)


@dataclass(frozen=True)
class _LegacyContainerMetadata:
    """Represent legacy detached container metadata."""

    instance_uuid: Optional[str]
    resource_id: Optional[int]
    connection_id: Optional[str]
    has_local_changes: bool


@dataclass(frozen=True)
class _LegacyContainerCandidate:
    """Represent a detached container outside the current layout."""

    source_path: Path
    legacy_instance_uuid: str
    legacy_resource_id: Optional[int]


class LegacyCacheMigrator:
    """Migrate production containers and purge indexed beta caches."""

    _UUID_PATTERN = re.compile(
        r"^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-"
        r"[89ab][a-f0-9]{3}-[a-f0-9]{12}$",
        re.IGNORECASE,
    )

    def __init__(
        self,
        cache_root: Path,
        project_usage: Optional[ProjectStorageUsage] = None,
        *,
        target_cache_root: Optional[Path] = None,
    ) -> None:
        """Initialize legacy cache migrator."""
        self._cache_root = Path(cache_root)
        self._target_cache_root = (
            self._cache_root
            if target_cache_root is None
            else Path(target_cache_root)
        )
        self._layer_store = DetachedLayerStore(self._target_cache_root)
        self._project_usage = project_usage or EmptyProjectStorageUsage()

    def need_migration(self) -> bool:
        """Return whether a legacy layout or indexed beta cache exists."""
        return bool(self._beta_cache_roots()) or any(
            True for _ in self._legacy_container_candidates()
        )

    def can_migrate(self) -> bool:
        """Return whether migration can run safely now."""
        used_paths = normalize_used_paths(self._project_usage.used_paths())
        source_paths = [
            candidate.source_path
            for candidate in self._legacy_container_candidates()
        ]

        if any(self._is_used(path, used_paths) for path in source_paths):
            return False
        return not self._lock_path.exists()

    def dry_run(self) -> MigrationReport:
        """Inspect migration actions without changing files."""
        return self._migrate(dry_run=True)

    def migrate(self) -> MigrationReport:
        """Migrate legacy storage and remove beta cache data."""
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
        beta_directories = self._beta_cache_roots()
        legacy_candidates = list(self._legacy_container_candidates())

        for beta_directory in beta_directories:
            self._purge_beta_cache(
                beta_directory,
                report,
                dry_run=dry_run,
            )

        for candidate in legacy_candidates:
            report.scanned_files += 1
            self._migrate_candidate(
                candidate,
                report,
                used_paths=used_paths,
                dry_run=dry_run,
            )
        return report

    def _purge_beta_cache(
        self,
        beta_directory: Path,
        report: MigrationReport,
        *,
        dry_run: bool,
    ) -> None:
        """Delete every artifact created by indexed beta storage."""
        for hash_directory in self._beta_hash_directories(beta_directory):
            self._delete_tree(hash_directory, report, dry_run=dry_run)

        for index_path in beta_directory.glob("storage.sqlite*"):
            if not index_path.is_file():
                continue
            report.scanned_files += 1
            if dry_run:
                report.deleted_files += 1
                continue
            try:
                index_path.unlink()
                report.deleted_files += 1
            except OSError as error:
                report.blocked_files += 1
                report.errors.append(str(error))

        if dry_run:
            return

        if beta_directory == self._cache_root:
            self._remove_empty_child_directories(beta_directory)
        else:
            self._remove_empty_directories(beta_directory)

    def _migrate_candidate(
        self,
        candidate: _LegacyContainerCandidate,
        report: MigrationReport,
        *,
        used_paths: Iterable[Path],
        dry_run: bool,
    ) -> None:
        """Migrate one detached container candidate."""
        metadata = self._read_metadata(candidate.source_path)
        if metadata is None:
            report.skipped_files += 1
            report.warnings.append(
                "Detached container is invalid and was left untouched: "
                f"{candidate.source_path}"
            )
            return

        instance_uuid = (
            metadata.instance_uuid or candidate.legacy_instance_uuid
        )
        resource_id = metadata.resource_id
        if resource_id is None:
            resource_id = candidate.legacy_resource_id
        if resource_id is None:
            report.skipped_files += 1
            report.warnings.append(
                "Could not determine resource id for detached container: "
                f"{candidate.source_path}"
            )
            return

        if self._is_used(candidate.source_path, used_paths):
            report.blocked_files += 1
            report.warnings.append(
                "Container is still used by the current project: "
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
                layer_key,
                metadata,
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
                is_used_by_project=False,
            )
            if entry.id is None:
                raise StorageMigrationError(
                    "Migrated container has no index entry id",
                    path=target_path,
                )
            self._move_service_files(candidate.source_path, target_path)
            candidate.source_path.unlink(missing_ok=True)
            self._remove_empty_legacy_directories(candidate.source_path.parent)
        except Exception as error:
            report.errors.append(str(error))
            report.blocked_files += 1
            return

        report.migrated_files += 1

    def _handle_existing_target(
        self,
        candidate: _LegacyContainerCandidate,
        layer_key: LayerKey,
        metadata: _LegacyContainerMetadata,
        target_path: Path,
        report: MigrationReport,
    ) -> None:
        """Handle migration when the target already exists."""
        if not self._same_file(candidate.source_path, target_path):
            report.blocked_files += 1
            report.errors.append(
                "Migration target already exists with different content: "
                f"{target_path}"
            )
            return

        try:
            self._layer_store.ensure_container_entry(
                layer_key,
                connection_id=metadata.connection_id,
                has_local_changes=metadata.has_local_changes,
                is_used_by_project=False,
            )
            self._move_service_files(candidate.source_path, target_path)
            candidate.source_path.unlink(missing_ok=True)
            self._remove_empty_legacy_directories(candidate.source_path.parent)
        except Exception as error:
            report.errors.append(str(error))
            report.blocked_files += 1
            return
        report.migrated_files += 1

    def _legacy_container_candidates(
        self,
    ) -> Iterable[_LegacyContainerCandidate]:
        """Yield production containers from the flat legacy layout."""
        if not self._cache_root.exists():
            return []

        candidates: List[_LegacyContainerCandidate] = []
        for instance_directory in self._instance_directories():
            for gpkg_path in instance_directory.glob("*.gpkg"):
                candidates.append(
                    self._candidate(gpkg_path, instance_directory.name)
                )
        return candidates

    def _candidate(
        self,
        path: Path,
        instance_uuid: str,
    ) -> _LegacyContainerCandidate:
        """Create a detached container migration candidate."""
        return _LegacyContainerCandidate(
            source_path=path,
            legacy_instance_uuid=instance_uuid,
            legacy_resource_id=self._parse_int(path.stem),
        )

    def _beta_cache_roots(self) -> List[Path]:
        """Return indexed cache roots created by beta builds."""
        beta_roots: List[Path] = []
        if self._is_root_beta_cache():
            beta_roots.append(self._cache_root)
        beta_roots.extend(self._beta_instance_directories())
        return beta_roots

    def _beta_instance_directories(self) -> List[Path]:
        """Return per-instance indexed cache directories from beta builds."""
        return [
            directory
            for directory in self._instance_directories()
            if any(
                path.is_file() for path in directory.glob("storage.sqlite*")
            )
            or any(True for _ in self._beta_hash_directories(directory))
        ]

    def _is_root_beta_cache(self) -> bool:
        """Return whether cache root contains disposable beta index data."""
        index_path = StoragePathResolver(self._cache_root).index_path()
        if not index_path.exists():
            return False
        return not self._is_current_index(index_path)

    def _instance_directories(self) -> List[Path]:
        """Return legacy instance directories below the source cache root."""
        if not self._cache_root.exists():
            return []
        return [
            path
            for path in self._cache_root.iterdir()
            if path.is_dir() and self._UUID_PATTERN.match(path.name)
        ]

    def _beta_hash_directories(
        self,
        beta_directory: Path,
    ) -> Iterable[Path]:
        """Yield hash directories created by beta storage versions."""
        if not beta_directory.exists():
            return []

        hash_directories: List[Path] = []
        for prefix_directory in beta_directory.iterdir():
            if prefix_directory.is_symlink() or not prefix_directory.is_dir():
                continue
            for hash_directory in prefix_directory.iterdir():
                if hash_directory.is_symlink() or not hash_directory.is_dir():
                    continue
                probe_path = hash_directory / "entry"
                if StoragePathResolver.is_indexed_storage_path(probe_path):
                    hash_directories.append(hash_directory)
        return hash_directories

    def _delete_tree(
        self,
        root: Path,
        report: MigrationReport,
        *,
        dry_run: bool,
    ) -> None:
        """Delete a beta hash tree without retaining its contents."""
        for current_root, directory_names, file_names in os.walk(
            str(root),
            topdown=False,
        ):
            current_path = Path(current_root)
            for file_name in file_names:
                file_path = current_path / file_name
                report.scanned_files += 1
                if dry_run:
                    report.deleted_files += 1
                    continue
                try:
                    file_path.unlink()
                    report.deleted_files += 1
                except OSError as error:
                    report.blocked_files += 1
                    report.errors.append(str(error))

            if dry_run:
                continue
            for directory_name in directory_names:
                directory_path = current_path / directory_name
                try:
                    if directory_path.is_symlink():
                        directory_path.unlink()
                    else:
                        directory_path.rmdir()
                except OSError as error:
                    report.blocked_files += 1
                    report.errors.append(str(error))

        if dry_run:
            return
        try:
            root.rmdir()
        except OSError as error:
            report.blocked_files += 1
            report.errors.append(str(error))

    def _is_current_index(self, index_path: Path) -> bool:
        """Return whether an index belongs to the current storage schema."""
        try:
            with sqlite3.connect(str(index_path)) as connection:
                row = connection.execute(
                    "SELECT version FROM storage_schema LIMIT 1"
                ).fetchone()
        except sqlite3.DatabaseError:
            return False

        if row is None:
            return False

        try:
            return int(row[0]) == SCHEMA_VERSION
        except (TypeError, ValueError):
            return False

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
                return _LegacyContainerMetadata(
                    instance_uuid=metadata.get("instance_id"),
                    resource_id=self._parse_int(metadata.get("resource_id")),
                    connection_id=metadata.get("connection_id"),
                    has_local_changes=self._has_local_changes(cursor),
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
                if not self._same_file(service_file, target_file):
                    raise StorageMigrationError(
                        "GeoPackage service file target has different content",
                        path=target_file,
                    )
                service_file.unlink(missing_ok=True)
                continue
            target_file.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(service_file), str(target_file))

    def _remove_empty_legacy_directories(self, start_directory: Path) -> None:
        """Remove empty legacy directories below the source cache root."""
        current_directory = start_directory
        while current_directory != self._cache_root:
            try:
                current_directory.rmdir()
            except OSError:
                return
            current_directory = current_directory.parent

    def _remove_empty_directories(self, root: Path) -> None:
        """Remove empty directories below and including a legacy root."""
        if not root.exists():
            return

        for current_root, directory_names, _ in os.walk(
            str(root),
            topdown=False,
        ):
            current_path = Path(current_root)
            for directory_name in directory_names:
                try:
                    (current_path / directory_name).rmdir()
                except OSError:
                    continue
        try:
            root.rmdir()
        except OSError:
            pass

    def _remove_empty_child_directories(self, root: Path) -> None:
        """Remove empty directories below a root while keeping the root."""
        if not root.exists():
            return

        for path in sorted(root.iterdir(), reverse=True):
            if not path.is_dir():
                continue
            self._remove_empty_directories(path)

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
        return self._normalized_path(path) in used_paths

    def _normalized_path(self, path: Path) -> Path:
        """Return a path normalized for project usage comparisons."""
        try:
            return path.resolve()
        except OSError:
            return path

    def _parse_int(self, value: object) -> Optional[int]:
        """Parse an integer value."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
