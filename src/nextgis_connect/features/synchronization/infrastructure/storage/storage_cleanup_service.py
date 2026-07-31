import time
from pathlib import Path
from typing import Dict, List, Optional

from nextgis_connect.platform.storage.garbage_collector import (
    CachePurgePolicy,
    GarbageCollector,
    StorageCleanupReport,
)
from nextgis_connect.platform.storage.models import (
    StorageEntry,
    StorageEntryProtection,
)
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)


class StorageCleanupService:
    """Clean local storage without losing user data."""

    def __init__(self, cache_root: Path) -> None:
        """Initialize storage cleanup service."""
        self._path_resolver = StoragePathResolver(Path(cache_root))

    def purge(self, policy: CachePurgePolicy) -> StorageCleanupReport:
        """Purge disposable storage entries."""
        report = StorageCleanupReport()
        for storage_index in self._indexes(policy.instance_uuid):
            collector = GarbageCollector(self._path_resolver, storage_index)
            partial_report = collector.purge(policy)
            self._merge_report(report, partial_report)
        return report

    def clear_disposable_cache(
        self,
        *,
        delete_referenced_attachments: bool = False,
    ) -> StorageCleanupReport:
        """Clear only disposable cache entries."""
        return self.purge(
            CachePurgePolicy(
                delete_referenced_attachments=delete_referenced_attachments,
            )
        )

    def purge_automatic(
        self,
        *,
        max_size_bytes: Optional[int],
        max_age_days: Optional[int],
    ) -> StorageCleanupReport:
        """Purge disposable entries according to startup cache limits."""
        report = StorageCleanupReport()
        selected_entries_by_index: Dict[
            SqliteStorageIndex,
            List[StorageEntry],
        ] = {}
        current_size = self._cache_size_bytes()
        cutoff_time = (
            None
            if max_age_days is None
            else time.time() - max_age_days * 24 * 60 * 60
        )

        for storage_index in self._indexes(None):
            collector = GarbageCollector(self._path_resolver, storage_index)
            candidates = collector.candidates(CachePurgePolicy())
            selected_entries = self._entries_expired_by_age(
                candidates,
                cutoff_time,
            )
            selected_entry_ids = {
                entry.id for entry in selected_entries if entry.id is not None
            }
            current_size -= self._entries_size_bytes(selected_entries)

            if max_size_bytes is not None and current_size > max_size_bytes:
                for entry in self._sort_entries_for_size_purge(candidates):
                    if entry.id in selected_entry_ids:
                        continue

                    selected_entries.append(entry)
                    selected_entry_ids.add(entry.id)
                    current_size -= self._entry_size_bytes(entry)
                    if current_size <= max_size_bytes:
                        break

            if selected_entries:
                selected_entries_by_index[storage_index] = selected_entries

        for storage_index, entries in selected_entries_by_index.items():
            collector = GarbageCollector(self._path_resolver, storage_index)
            partial_report = collector.delete_entries(entries)
            self._merge_report(report, partial_report)

        return report

    def clear_connection_cache(
        self,
        instance_uuid: str,
        *,
        discard_dirty: bool = False,
    ) -> StorageCleanupReport:
        """Clear cache for one instance when it is safe."""
        storage_index = self._index_for_instance(instance_uuid)
        dirty_entries = self._dirty_entries(storage_index, instance_uuid)
        if dirty_entries and not discard_dirty:
            return StorageCleanupReport(
                blocked_files=len(dirty_entries),
                warnings=[
                    "Dirty storage entries were kept because discard_dirty is "
                    "False"
                ],
            )

        if discard_dirty:
            collector = GarbageCollector(self._path_resolver, storage_index)
            return collector.delete_entries(
                storage_index.entries_for_instance(instance_uuid)
            )

        collector = GarbageCollector(self._path_resolver, storage_index)
        return collector.purge(
            CachePurgePolicy(
                instance_uuid=instance_uuid,
                delete_referenced_attachments=True,
            )
        )

    def clear_resource_cache(
        self,
        instance_uuid: str,
        resource_id: int,
        *,
        discard_dirty: bool = False,
    ) -> StorageCleanupReport:
        """Clear cache entries for one resource when it is safe."""
        storage_index = self._index_for_instance(instance_uuid)
        entries = [
            entry
            for entry in storage_index.entries_for_resource(int(resource_id))
            if entry.instance_uuid == instance_uuid
        ]
        dirty_entries = self._dirty_entries_from(entries)
        if dirty_entries and not discard_dirty:
            return StorageCleanupReport(
                blocked_files=len(dirty_entries),
                warnings=[
                    "Dirty storage entries were kept because discard_dirty is "
                    "False"
                ],
            )

        collector = GarbageCollector(self._path_resolver, storage_index)
        return collector.delete_entries(entries)

    def _indexes(
        self,
        instance_uuid: Optional[str],
    ) -> List[SqliteStorageIndex]:
        """Return initialized storage indexes."""
        if instance_uuid is not None:
            return [self._index_for_instance(instance_uuid)]

        indexes: List[SqliteStorageIndex] = []
        if not self._path_resolver.cache_root.exists():
            return indexes

        for index_path in self._path_resolver.cache_root.glob(
            "*/storage.sqlite"
        ):
            storage_index = SqliteStorageIndex(index_path)
            storage_index.initialize()
            indexes.append(storage_index)
        return indexes

    def _index_for_instance(self, instance_uuid: str) -> SqliteStorageIndex:
        """Return storage index for an instance."""
        storage_index = SqliteStorageIndex(
            self._path_resolver.index_path(instance_uuid)
        )
        storage_index.initialize()
        return storage_index

    def _dirty_entries(
        self,
        storage_index: SqliteStorageIndex,
        instance_uuid: str,
    ) -> List[StorageEntry]:
        """Return dirty or rollback-protected entries."""
        return self._dirty_entries_from(
            storage_index.entries_for_instance(instance_uuid)
        )

    def _dirty_entries_from(
        self,
        entries: List[StorageEntry],
    ) -> List[StorageEntry]:
        """Return dirty or rollback-protected entries from a list."""
        dirty_protections = {
            StorageEntryProtection.DIRTY,
            StorageEntryProtection.RETAIN_FOR_ROLLBACK,
            StorageEntryProtection.USED_BY_PROJECT,
            StorageEntryProtection.LEASED,
        }
        return [
            entry for entry in entries if entry.protection in dirty_protections
        ]

    def _entries_expired_by_age(
        self,
        entries: List[StorageEntry],
        cutoff_time: Optional[float],
    ) -> List[StorageEntry]:
        """Return entries whose cache files are older than the cutoff."""
        if cutoff_time is None:
            return []

        return [
            entry
            for entry in entries
            if self._entry_last_used_time(entry) <= cutoff_time
        ]

    def _sort_entries_for_size_purge(
        self,
        entries: List[StorageEntry],
    ) -> List[StorageEntry]:
        """Sort disposable entries by least recent file use."""
        return sorted(entries, key=self._entry_last_used_time)

    def _entry_last_used_time(self, entry: StorageEntry) -> float:
        """Return the last known file usage timestamp for an entry."""
        path = self._path_resolver.absolute_from_entry(
            entry.instance_uuid,
            entry.relative_path,
        )
        if not path.exists():
            return 0

        file_stat = path.stat()
        return max(file_stat.st_atime, file_stat.st_mtime)

    def _entries_size_bytes(self, entries: List[StorageEntry]) -> int:
        """Return existing file size for a collection of entries."""
        return sum(self._entry_size_bytes(entry) for entry in entries)

    def _entry_size_bytes(self, entry: StorageEntry) -> int:
        """Return existing file size for an entry."""
        path = self._path_resolver.absolute_from_entry(
            entry.instance_uuid,
            entry.relative_path,
        )
        if not path.exists() or not path.is_file():
            return 0
        return path.stat().st_size

    def _cache_size_bytes(self) -> int:
        """Return current non-metadata cache size in bytes."""
        cache_root = self._path_resolver.cache_root
        if not cache_root.exists():
            return 0

        size = 0
        for path in cache_root.glob("**/*"):
            if not path.is_file() or self._is_storage_metadata_file(path):
                continue
            size += path.stat().st_size
        return size

    def _is_storage_metadata_file(self, path: Path) -> bool:
        """Return whether a path belongs to storage metadata."""
        file_name = path.name
        return (
            file_name == "storage.sqlite"
            or file_name.startswith("storage.sqlite-")
            or file_name == ".storage_migration.lock"
        )

    def _merge_report(
        self,
        target: StorageCleanupReport,
        source: StorageCleanupReport,
    ) -> None:
        """Merge cleanup report data."""
        target.deleted_files += source.deleted_files
        target.skipped_files += source.skipped_files
        target.blocked_files += source.blocked_files
        target.errors.extend(source.errors)
        target.warnings.extend(source.warnings)
        target.deleted_paths.extend(source.deleted_paths)
