from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional

from nextgis_connect.platform.storage.errors import StorageCleanupError
from nextgis_connect.platform.storage.models import (
    StorageEntry,
    StorageEntryKind,
)
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)


@dataclass(frozen=True)
class CachePurgePolicy:
    """Describe a cache purge policy."""

    instance_uuid: Optional[str] = None
    discard_dirty: bool = False


@dataclass
class StorageCleanupReport:
    """Describe storage cleanup results."""

    deleted_files: int = 0
    skipped_files: int = 0
    blocked_files: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    deleted_paths: List[Path] = field(default_factory=list)


class GarbageCollector:
    """Remove disposable indexed files."""

    def __init__(
        self,
        path_resolver: StoragePathResolver,
        storage_index: SqliteStorageIndex,
    ) -> None:
        """Initialize garbage collector."""
        self._path_resolver = path_resolver
        self._storage_index = storage_index

    def candidates(
        self,
        policy: Optional[CachePurgePolicy] = None,
    ) -> List[StorageEntry]:
        """Return cleanup candidates."""
        policy = policy or CachePurgePolicy()
        candidates = self._storage_index.gc_candidates()
        if policy.instance_uuid is None:
            return self._sort_entries(candidates)
        return self._sort_entries(
            entry
            for entry in candidates
            if entry.instance_uuid == policy.instance_uuid
        )

    def purge(
        self,
        policy: Optional[CachePurgePolicy] = None,
    ) -> StorageCleanupReport:
        """Purge disposable storage entries."""
        return self.delete_entries(self.candidates(policy))

    def delete_entries(
        self,
        entries: Iterable[StorageEntry],
    ) -> StorageCleanupReport:
        """Delete selected storage entries."""
        report = StorageCleanupReport()
        for entry in self._sort_entries(entries):
            if entry.id is None:
                report.skipped_files += 1
                continue

            absolute_path = self._path_resolver.absolute_from_entry(
                entry.instance_uuid,
                entry.relative_path,
            )
            try:
                self._delete_path(absolute_path, entry)
                self._storage_index.delete_entry(entry.id)
                report.deleted_files += 1
                report.deleted_paths.append(absolute_path)
            except Exception as error:
                report.errors.append(str(error))
                report.blocked_files += 1

        self._remove_empty_dirs()
        return report

    def _delete_path(
        self,
        absolute_path: Path,
        entry: StorageEntry,
    ) -> None:
        """Delete one indexed path."""
        if not absolute_path.exists():
            return

        if absolute_path.is_dir():
            raise StorageCleanupError(
                "Refusing to delete directory storage entry",
                path=absolute_path,
                storage_key=entry.storage_key.seed,
            )

        if entry.kind == StorageEntryKind.LAYER_CONTAINER:
            for service_file in absolute_path.parent.glob(
                f"{absolute_path.name}-*"
            ):
                if service_file.is_file():
                    service_file.unlink()

        absolute_path.unlink()

    def _sort_entries(
        self,
        entries: Iterable[StorageEntry],
    ) -> List[StorageEntry]:
        """Sort entries by cleanup priority."""
        priority = {
            StorageEntryKind.TEMPORARY_FILE: 0,
            StorageEntryKind.ATTACHMENT_PREVIEW: 1,
            StorageEntryKind.ATTACHMENT_BLOB: 3,
            StorageEntryKind.LAYER_CONTAINER: 5,
            StorageEntryKind.SERVICE_FILE: 6,
            StorageEntryKind.UNKNOWN_LEGACY_FILE: 99,
        }
        return sorted(
            entries,
            key=lambda entry: (
                priority.get(entry.kind, 50),
                entry.relative_path.as_posix(),
            ),
        )

    def _remove_empty_dirs(self) -> None:
        """Remove empty storage directories."""
        root = self._path_resolver.cache_root
        if not root.exists():
            return

        directories = [path for path in root.rglob("*") if path.is_dir()]
        directories.sort(key=lambda path: len(path.parts), reverse=True)
        for directory in directories:
            try:
                directory.rmdir()
            except OSError:
                continue
