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

from pathlib import Path
from typing import Optional

from nextgis_connect.platform.storage.file_store import FileStore
from nextgis_connect.platform.storage.models import (
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


class DetachedLayerStore:
    """Manage detached layer containers in local storage."""

    def __init__(self, cache_root: Path) -> None:
        """Initialize detached layer store."""
        self._path_resolver = StoragePathResolver(Path(cache_root))
        self._storage_index = SqliteStorageIndex(
            self._path_resolver.index_path()
        )

    def container_path(self, layer_key: LayerKey) -> Path:
        """Return the canonical detached container path."""
        storage_key = StorageKeyFactory.layer_container(layer_key)
        return self._path_resolver.resolve(
            storage_key,
            self._container_file_name(layer_key),
        )

    def ensure_container_entry(
        self,
        layer_key: LayerKey,
        source_path: Optional[Path] = None,
        *,
        connection_id: Optional[str] = None,
        has_local_changes: bool = False,
        is_used_by_project: bool = False,
        overwrite: bool = False,
    ) -> StorageEntry:
        """Ensure a storage entry exists for a detached container."""
        storage_key = StorageKeyFactory.layer_container(layer_key)
        storage_index = self._storage_index
        file_store = FileStore(self._path_resolver, storage_index)
        protection = self._container_protection(
            has_local_changes=has_local_changes,
            is_used_by_project=is_used_by_project,
        )
        target_path = self.container_path(layer_key)

        if source_path is not None and Path(source_path) != target_path:
            blob_ref = file_store.copy_from(
                storage_key,
                self._container_file_name(layer_key),
                Path(source_path),
                kind=StorageEntryKind.LAYER_CONTAINER,
                resource_id=layer_key.resource_id,
                state=StorageEntryState.COMMITTED,
                protection=protection,
                overwrite=overwrite,
            )
            entry = storage_index.find_entry(blob_ref.storage_key)
        else:
            entry = file_store.ensure_entry_for_existing_file(
                storage_key,
                self._container_file_name(layer_key),
                kind=StorageEntryKind.LAYER_CONTAINER,
                resource_id=layer_key.resource_id,
                state=StorageEntryState.COMMITTED,
                protection=protection,
            )

        assert entry is not None
        assert entry.id is not None
        storage_index.upsert_layer_entry(
            resource_id=layer_key.resource_id,
            container_entry_id=entry.id,
            connection_id=connection_id,
            instance_uuid=layer_key.instance_uuid,
            has_local_changes=has_local_changes,
            is_used_by_project=is_used_by_project,
            last_sync_state=None,
        )
        return entry

    def _container_file_name(self, layer_key: LayerKey) -> str:
        """Return the stable detached container file name."""
        return f"{layer_key.resource_id}.gpkg"

    def ensure_container_placeholder(
        self,
        layer_key: LayerKey,
        *,
        connection_id: Optional[str] = None,
    ) -> StorageEntry:
        """Ensure an index placeholder exists for a detached container."""
        storage_key = StorageKeyFactory.layer_container(layer_key)
        storage_index = self._storage_index
        absolute_path = self.container_path(layer_key)
        relative_path = self._path_resolver.relative_to_cache(absolute_path)
        entry = storage_index.upsert_entry(
            StorageEntry(
                id=None,
                storage_key=storage_key,
                kind=StorageEntryKind.LAYER_CONTAINER,
                relative_path=relative_path,
                instance_uuid=layer_key.instance_uuid,
                resource_id=layer_key.resource_id,
                size_bytes=0,
                sha256=None,
                state=StorageEntryState.COMMITTED,
                protection=StorageEntryProtection.NONE,
            )
        )
        assert entry.id is not None
        storage_index.upsert_layer_entry(
            resource_id=layer_key.resource_id,
            container_entry_id=entry.id,
            connection_id=connection_id,
            instance_uuid=layer_key.instance_uuid,
            has_local_changes=False,
            is_used_by_project=False,
            last_sync_state=None,
        )
        return entry

    def mark_used_by_project(self, layer_key: LayerKey, used: bool) -> None:
        """Update project usage protection for a layer container."""
        self._update_layer_flags(layer_key, is_used_by_project=used)

    def mark_has_local_changes(
        self,
        layer_key: LayerKey,
        has_changes: bool,
    ) -> None:
        """Update dirty protection for a layer container."""
        self._update_layer_flags(layer_key, has_local_changes=has_changes)

    def release_layer(self, layer_key: LayerKey) -> None:
        """Release a layer from project usage."""
        self.mark_used_by_project(layer_key, False)

    def _update_layer_flags(
        self,
        layer_key: LayerKey,
        *,
        has_local_changes: Optional[bool] = None,
        is_used_by_project: Optional[bool] = None,
    ) -> None:
        """Update layer index flags and entry protection."""
        storage_index = self._storage_index
        layer_entry = storage_index.layer_entry(layer_key)
        if layer_entry is None:
            return

        entry = storage_index.find_entry_by_id(
            int(layer_entry["container_entry_id"])
        )
        if entry is None:
            return

        next_has_local_changes = (
            bool(layer_entry["has_local_changes"])
            if has_local_changes is None
            else has_local_changes
        )
        next_is_used_by_project = (
            bool(layer_entry["is_used_by_project"])
            if is_used_by_project is None
            else is_used_by_project
        )
        next_protection = self._container_protection(
            has_local_changes=next_has_local_changes,
            is_used_by_project=next_is_used_by_project,
        )
        storage_index.update_entry(
            StorageEntry(
                id=entry.id,
                storage_key=entry.storage_key,
                kind=entry.kind,
                relative_path=entry.relative_path,
                instance_uuid=entry.instance_uuid,
                resource_id=entry.resource_id,
                size_bytes=entry.size_bytes,
                sha256=entry.sha256,
                state=entry.state,
                protection=next_protection,
            )
        )
        storage_index.upsert_layer_entry(
            resource_id=layer_key.resource_id,
            container_entry_id=entry.id,
            connection_id=layer_entry["connection_id"],
            instance_uuid=layer_key.instance_uuid,
            has_local_changes=next_has_local_changes,
            is_used_by_project=next_is_used_by_project,
            last_sync_state=layer_entry["last_sync_state"],
        )

    def _container_protection(
        self,
        *,
        has_local_changes: bool,
        is_used_by_project: bool,
    ) -> StorageEntryProtection:
        """Return protection for layer container state."""
        if has_local_changes:
            return StorageEntryProtection.DIRTY
        if is_used_by_project:
            return StorageEntryProtection.USED_BY_PROJECT
        return StorageEntryProtection.NONE
