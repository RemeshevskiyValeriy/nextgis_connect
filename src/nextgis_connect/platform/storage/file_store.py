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
from pathlib import Path
from typing import Optional

from nextgis_connect.platform.storage.atomic_file_writer import (
    AtomicFileWriter,
)
from nextgis_connect.platform.storage.models import (
    BlobRef,
    StorageEntry,
    StorageEntryKind,
    StorageEntryProtection,
    StorageEntryState,
    StorageKey,
)
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)


class FileStore:
    """Store files and register them in the storage index."""

    def __init__(
        self,
        path_resolver: StoragePathResolver,
        storage_index: SqliteStorageIndex,
        writer: Optional[AtomicFileWriter] = None,
    ) -> None:
        """Initialize file store."""
        self._path_resolver = path_resolver
        self._storage_index = storage_index
        self._writer = writer or AtomicFileWriter()

    def write_bytes(
        self,
        storage_key: StorageKey,
        file_name: str,
        data: bytes,
        *,
        kind: StorageEntryKind,
        resource_id: Optional[int],
        state: StorageEntryState,
        protection: StorageEntryProtection,
        overwrite: bool = False,
    ) -> BlobRef:
        """Write bytes and register a storage entry."""
        target_path = self._path_resolver.resolve(
            storage_key,
            file_name,
            create_parent=True,
        )
        result = self._writer.write_bytes(
            target_path,
            data,
            overwrite=overwrite,
        )
        entry = self._entry_from_result(
            storage_key=storage_key,
            file_name=file_name,
            kind=kind,
            resource_id=resource_id,
            state=state,
            protection=protection,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
        )
        stored_entry = self._storage_index.upsert_entry(entry)
        return BlobRef(
            storage_key=storage_key,
            entry_id=stored_entry.id,
            path=target_path,
        )

    def copy_from(
        self,
        storage_key: StorageKey,
        file_name: str,
        source_path: Path,
        *,
        kind: StorageEntryKind,
        resource_id: Optional[int],
        state: StorageEntryState,
        protection: StorageEntryProtection,
        overwrite: bool = False,
    ) -> BlobRef:
        """Copy a file and register a storage entry."""
        target_path = self._path_resolver.resolve(
            storage_key,
            file_name,
            create_parent=True,
        )
        result = self._writer.copy_from(
            source_path,
            target_path,
            overwrite=overwrite,
        )
        entry = self._entry_from_result(
            storage_key=storage_key,
            file_name=file_name,
            kind=kind,
            resource_id=resource_id,
            state=state,
            protection=protection,
            size_bytes=result.size_bytes,
            sha256=result.sha256,
        )
        stored_entry = self._storage_index.upsert_entry(entry)
        return BlobRef(
            storage_key=storage_key,
            entry_id=stored_entry.id,
            path=target_path,
        )

    def ensure_entry_for_existing_file(
        self,
        storage_key: StorageKey,
        file_name: str,
        *,
        kind: StorageEntryKind,
        resource_id: Optional[int],
        state: StorageEntryState,
        protection: StorageEntryProtection,
    ) -> StorageEntry:
        """Register an existing file in the storage index."""
        target_path = self._path_resolver.resolve(storage_key, file_name)
        file_stat = target_path.stat()
        entry = self._entry_from_result(
            storage_key=storage_key,
            file_name=file_name,
            kind=kind,
            resource_id=resource_id,
            state=state,
            protection=protection,
            size_bytes=file_stat.st_size,
            sha256=self._sha256(target_path),
        )
        return self._storage_index.upsert_entry(entry)

    def _entry_from_result(
        self,
        *,
        storage_key: StorageKey,
        file_name: str,
        kind: StorageEntryKind,
        resource_id: Optional[int],
        state: StorageEntryState,
        protection: StorageEntryProtection,
        size_bytes: int,
        sha256: str,
    ) -> StorageEntry:
        """Create a storage entry from file data."""
        absolute_path = self._path_resolver.resolve(storage_key, file_name)
        relative_path = self._path_resolver.relative_to_cache(absolute_path)
        return StorageEntry(
            id=None,
            storage_key=storage_key,
            kind=kind,
            relative_path=relative_path,
            instance_uuid=storage_key.instance_uuid,
            resource_id=resource_id,
            size_bytes=size_bytes,
            sha256=sha256,
            state=state,
            protection=protection,
        )

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
