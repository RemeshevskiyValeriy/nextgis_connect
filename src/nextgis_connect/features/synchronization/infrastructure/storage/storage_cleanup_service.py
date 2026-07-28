from pathlib import Path
from typing import List, Optional

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

    def clear_disposable_cache(self) -> StorageCleanupReport:
        """Clear only disposable cache entries."""
        return self.purge(CachePurgePolicy())

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
        return collector.purge(CachePurgePolicy(instance_uuid=instance_uuid))

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
        dirty_protections = {
            StorageEntryProtection.DIRTY,
            StorageEntryProtection.RETAIN_FOR_ROLLBACK,
            StorageEntryProtection.USED_BY_PROJECT,
            StorageEntryProtection.LEASED,
        }
        return [
            entry
            for entry in storage_index.entries_for_instance(instance_uuid)
            if entry.protection in dirty_protections
        ]

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
