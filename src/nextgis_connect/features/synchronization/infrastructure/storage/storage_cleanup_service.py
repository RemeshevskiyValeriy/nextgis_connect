import time
from pathlib import Path
from typing import List, Optional

from nextgis_connect.platform.storage.garbage_collector import (
    CachePurgePolicy,
    GarbageCollector,
    StorageCleanupReport,
)
from nextgis_connect.platform.storage.models import (
    LayerKey,
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
        self._storage_index = SqliteStorageIndex(
            self._path_resolver.index_path()
        )

    def purge(self, policy: CachePurgePolicy) -> StorageCleanupReport:
        """Purge disposable storage entries."""
        collector = GarbageCollector(
            self._path_resolver,
            self._storage_index,
        )
        return collector.purge(policy)

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
        selected_entries: List[StorageEntry] = []
        current_size = self._cache_size_bytes()
        cutoff_time = (
            None
            if max_age_days is None
            else time.time() - max_age_days * 24 * 60 * 60
        )

        collector = GarbageCollector(
            self._path_resolver,
            self._storage_index,
        )
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

        if not selected_entries:
            return report
        return collector.delete_entries(selected_entries)

    def cache_size_bytes(self) -> int:
        """Return the existing size of indexed cache files in bytes."""
        return self._entries_size_bytes(
            self._storage_index.entries_for_instance()
        )

    def clear_connection_cache(
        self,
        instance_uuid: str,
        *,
        discard_dirty: bool = False,
    ) -> StorageCleanupReport:
        """Clear cache for one instance when it is safe."""
        storage_index = self._storage_index
        dirty_entries = self._dirty_entries(storage_index, instance_uuid)
        if dirty_entries and not discard_dirty:
            return StorageCleanupReport(
                blocked_files=len(dirty_entries),
                warnings=[
                    (
                        "Dirty storage entries were kept because "
                        "discard_dirty is False"
                    )
                ],
            )

        collector = GarbageCollector(self._path_resolver, storage_index)
        if discard_dirty:
            return collector.delete_entries(
                storage_index.entries_for_instance(instance_uuid)
            )

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
        storage_index = self._storage_index
        entries = storage_index.entries_for_layer(
            LayerKey(instance_uuid, int(resource_id))
        )
        dirty_entries = self._dirty_entries_from(entries)
        if dirty_entries and not discard_dirty:
            return StorageCleanupReport(
                blocked_files=len(dirty_entries),
                warnings=[
                    (
                        "Dirty storage entries were kept because "
                        "discard_dirty is False"
                    )
                ],
            )

        collector = GarbageCollector(self._path_resolver, storage_index)
        return collector.delete_entries(entries)

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
            entry.relative_path,
        )
        if not path.is_file():
            return 0
        return path.stat().st_size

    def _cache_size_bytes(self) -> int:
        """Return current indexed cache size in bytes."""
        return self.cache_size_bytes()
