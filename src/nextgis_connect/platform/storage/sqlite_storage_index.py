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
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Sequence, Set

from nextgis_connect.platform.storage.errors import (
    StorageIndexError,
    StorageLeaseError,
)
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    LayerKey,
    StorageEntry,
    StorageEntryKind,
    StorageEntryProtection,
    StorageEntryState,
    StorageKey,
)
from nextgis_connect.platform.storage.storage_index_schema import (
    initialize_schema,
    utc_now_text,
)


class SqliteStorageIndex:
    """Persist storage metadata in a SQLite index."""

    def __init__(self, index_path: Path) -> None:
        """Initialize index repository."""
        self._index_path = Path(index_path)
        self._is_initialized = False

    @property
    def index_path(self) -> Path:
        """Return the SQLite index path."""
        return self._index_path

    def initialize(self) -> None:
        """Initialize storage index schema."""
        self._index_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with self._connect() as connection:
                connection.execute("PRAGMA journal_mode = WAL")
                initialize_schema(connection)
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not initialize storage index",
                path=self._index_path,
            ) from error
        self._is_initialized = True

    def add_entry(self, entry: StorageEntry) -> StorageEntry:
        """Add a storage entry."""
        self._ensure_initialized()
        now = utc_now_text()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO storage_entries (
                        storage_key, kind, relative_path, instance_uuid,
                        resource_id, size_bytes, sha256, state, protection,
                        created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    self._entry_values(entry, now),
                )
                return StorageEntry(
                    id=int(cursor.lastrowid),
                    storage_key=entry.storage_key,
                    kind=entry.kind,
                    relative_path=entry.relative_path,
                    instance_uuid=entry.instance_uuid,
                    resource_id=entry.resource_id,
                    size_bytes=entry.size_bytes,
                    sha256=entry.sha256,
                    state=entry.state,
                    protection=entry.protection,
                )
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not add storage entry",
                storage_key=entry.storage_key.seed,
                path=self._index_path,
            ) from error

    def upsert_entry(self, entry: StorageEntry) -> StorageEntry:
        """Add or update a storage entry."""
        existing_entry = self.find_entry(entry.storage_key)
        if existing_entry is None:
            return self.add_entry(entry)

        updated_entry = StorageEntry(
            id=existing_entry.id,
            storage_key=entry.storage_key,
            kind=entry.kind,
            relative_path=entry.relative_path,
            instance_uuid=entry.instance_uuid,
            resource_id=entry.resource_id,
            size_bytes=entry.size_bytes,
            sha256=entry.sha256,
            state=entry.state,
            protection=entry.protection,
        )
        self.update_entry(updated_entry)
        return updated_entry

    def update_entry(self, entry: StorageEntry) -> None:
        """Update a storage entry."""
        self._ensure_initialized()
        try:
            with self._transaction() as connection:
                cursor = connection.execute(
                    """
                    UPDATE storage_entries
                    SET kind = ?,
                        relative_path = ?,
                        instance_uuid = ?,
                        resource_id = ?,
                        size_bytes = ?,
                        sha256 = ?,
                        state = ?,
                        protection = ?,
                        updated_at = ?
                    WHERE id = ? OR storage_key = ?
                    """,
                    (
                        entry.kind.value,
                        entry.relative_path.as_posix(),
                        entry.instance_uuid,
                        entry.resource_id,
                        entry.size_bytes,
                        entry.sha256,
                        entry.state.value,
                        entry.protection.value,
                        utc_now_text(),
                        entry.id,
                        entry.storage_key.seed,
                    ),
                )
                if cursor.rowcount == 0:
                    raise StorageIndexError(
                        "Storage entry was not found",
                        storage_key=entry.storage_key.seed,
                    )
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not update storage entry",
                storage_key=entry.storage_key.seed,
                path=self._index_path,
            ) from error

    def find_entry(self, storage_key: StorageKey) -> Optional[StorageEntry]:
        """Find a storage entry by storage key."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT id, storage_key, kind, relative_path, instance_uuid,
                       resource_id, size_bytes, sha256, state, protection
                FROM storage_entries
                WHERE storage_key = ?
                """,
                (storage_key.seed,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return self._entry_from_row(row)

    def find_entry_by_id(self, entry_id: int) -> Optional[StorageEntry]:
        """Find a storage entry by row identifier."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT id, storage_key, kind, relative_path, instance_uuid,
                       resource_id, size_bytes, sha256, state, protection
                FROM storage_entries
                WHERE id = ?
                """,
                (entry_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return self._entry_from_row(row)

    def entries_for_resource(self, resource_id: int) -> List[StorageEntry]:
        """Return storage entries for a resource."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT id, storage_key, kind, relative_path, instance_uuid,
                       resource_id, size_bytes, sha256, state, protection
                FROM storage_entries
                WHERE resource_id = ?
                ORDER BY id
                """,
                (resource_id,),
            )
            rows = cursor.fetchall()
        return [self._entry_from_row(row) for row in rows]

    def entries_for_layer(self, layer_key: LayerKey) -> List[StorageEntry]:
        """Return storage entries for one resource in one Web GIS."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT id, storage_key, kind, relative_path, instance_uuid,
                       resource_id, size_bytes, sha256, state, protection
                FROM storage_entries
                WHERE instance_uuid = ? AND resource_id = ?
                ORDER BY id
                """,
                (layer_key.instance_uuid, layer_key.resource_id),
            )
            rows = cursor.fetchall()
        return [self._entry_from_row(row) for row in rows]

    def entries_for_instance(
        self,
        instance_uuid: Optional[str] = None,
    ) -> List[StorageEntry]:
        """Return storage entries for an instance."""
        self._ensure_initialized()
        with self._connect() as connection:
            if instance_uuid is None:
                cursor = connection.execute(
                    """
                    SELECT id, storage_key, kind, relative_path, instance_uuid,
                           resource_id, size_bytes, sha256, state, protection
                    FROM storage_entries
                    ORDER BY id
                    """
                )
            else:
                cursor = connection.execute(
                    """
                    SELECT id, storage_key, kind, relative_path, instance_uuid,
                           resource_id, size_bytes, sha256, state, protection
                    FROM storage_entries
                    WHERE instance_uuid = ?
                    ORDER BY id
                    """,
                    (instance_uuid,),
                )
            rows = cursor.fetchall()
        return [self._entry_from_row(row) for row in rows]

    def gc_candidates(
        self,
        *,
        delete_referenced_attachments: bool = False,
    ) -> List[StorageEntry]:
        """Return entries that can be considered for cleanup."""
        self._ensure_initialized()
        now = utc_now_text()
        states = (
            StorageEntryState.COMMITTED.value,
            StorageEntryState.ORPHANED.value,
            StorageEntryState.GC_CANDIDATE.value,
            StorageEntryState.TEMPORARY.value,
        )
        placeholders = ", ".join("?" for _ in states)
        params: List[object] = [
            *states,
            StorageEntryProtection.NONE.value,
            now,
        ]
        if delete_referenced_attachments:
            params.extend(
                [
                    StorageEntryKind.ATTACHMENT_BLOB.value,
                    StorageEntryKind.ATTACHMENT_PREVIEW.value,
                    AttachmentOperation.NONE.value,
                ]
            )
        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                SELECT entries.id, entries.storage_key, entries.kind,
                       entries.relative_path, entries.instance_uuid,
                       entries.resource_id, entries.size_bytes,
                       entries.sha256, entries.state, entries.protection
                FROM storage_entries AS entries
                LEFT JOIN layer_entries AS layers
                    ON layers.container_entry_id = entries.id
                WHERE entries.state IN ({placeholders})
                  AND entries.protection = ?
                  AND NOT EXISTS (
                      SELECT 1
                      FROM storage_leases AS leases
                      WHERE leases.entry_id = entries.id
                        AND (
                            leases.expires_at IS NULL
                            OR leases.expires_at > ?
                        )
                  )
                  {self._gc_reference_filter(delete_referenced_attachments)}
                  AND COALESCE(layers.has_local_changes, 0) = 0
                  AND COALESCE(layers.is_used_by_project, 0) = 0
                ORDER BY entries.id
                """,
                params,
            )
            rows = cursor.fetchall()
        return [self._entry_from_row(row) for row in rows]

    def acquire_lease(
        self,
        entry_id: int,
        owner: str,
        operation_id: str,
        expires_at: Optional[datetime],
    ) -> None:
        """Acquire a lease for a storage entry."""
        self._ensure_initialized()
        if self.find_entry_by_id(entry_id) is None:
            raise StorageLeaseError(
                "Cannot lease a missing storage entry",
                entry_id=entry_id,
                operation_id=operation_id,
            )

        expires_at_text = (
            None
            if expires_at is None
            else expires_at.replace(microsecond=0).isoformat()
        )
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO storage_leases (
                        entry_id, owner, operation_id, created_at, expires_at
                    )
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        entry_id,
                        owner,
                        operation_id,
                        utc_now_text(),
                        expires_at_text,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise StorageLeaseError(
                "Could not acquire storage lease",
                entry_id=entry_id,
                operation_id=operation_id,
            ) from error

    def release_lease(self, operation_id: str) -> None:
        """Release all leases for an operation."""
        self._ensure_initialized()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    DELETE FROM storage_leases
                    WHERE operation_id = ?
                    """,
                    (operation_id,),
                )
        except sqlite3.DatabaseError as error:
            raise StorageLeaseError(
                "Could not release storage lease",
                operation_id=operation_id,
            ) from error

    def active_lease_count(self, entry_id: int) -> int:
        """Return active lease count for an entry."""
        self._ensure_initialized()
        now = utc_now_text()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT COUNT(*)
                FROM storage_leases
                WHERE entry_id = ?
                  AND (expires_at IS NULL OR expires_at > ?)
                """,
                (entry_id, now),
            )
            return int(cursor.fetchone()[0])

    def delete_entry(self, entry_id: int) -> None:
        """Delete a storage entry from the index."""
        self._ensure_initialized()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    DELETE FROM storage_entries
                    WHERE id = ?
                    """,
                    (entry_id,),
                )
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not delete storage entry",
                entry_id=entry_id,
            ) from error

    def upsert_layer_entry(
        self,
        *,
        resource_id: int,
        container_entry_id: int,
        connection_id: Optional[str],
        instance_uuid: str,
        has_local_changes: bool,
        is_used_by_project: bool,
        last_sync_state: Optional[str],
    ) -> None:
        """Add or update a detached layer entry."""
        self._ensure_initialized()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO layer_entries (
                        resource_id, container_entry_id, connection_id,
                        instance_uuid, has_local_changes, is_used_by_project,
                        last_sync_state
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instance_uuid, resource_id) DO UPDATE SET
                        container_entry_id = excluded.container_entry_id,
                        connection_id = excluded.connection_id,
                        instance_uuid = excluded.instance_uuid,
                        has_local_changes = excluded.has_local_changes,
                        is_used_by_project = excluded.is_used_by_project,
                        last_sync_state = excluded.last_sync_state
                    """,
                    (
                        resource_id,
                        container_entry_id,
                        connection_id,
                        instance_uuid,
                        int(has_local_changes),
                        int(is_used_by_project),
                        last_sync_state,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not upsert layer entry",
                resource_id=resource_id,
                instance_uuid=instance_uuid,
            ) from error

    def layer_entry(
        self,
        layer_key: LayerKey,
    ) -> Optional[Dict[str, object]]:
        """Return a detached layer entry."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT resource_id, container_entry_id, connection_id,
                       instance_uuid, has_local_changes, is_used_by_project,
                       last_sync_state
                FROM layer_entries
                WHERE instance_uuid = ? AND resource_id = ?
                """,
                (layer_key.instance_uuid, layer_key.resource_id),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return self._layer_entry_from_row(row)

    def layer_entries(
        self,
        *,
        instance_uuid: Optional[str] = None,
        has_local_changes: Optional[bool] = None,
        is_used_by_project: Optional[bool] = None,
    ) -> List[Dict[str, object]]:
        """Return detached layer entries filtered by stored flags."""
        self._ensure_initialized()
        clauses: List[str] = []
        params: List[object] = []
        if instance_uuid is not None:
            clauses.append("layers.instance_uuid = ?")
            params.append(instance_uuid)
        if has_local_changes is not None:
            clauses.append("layers.has_local_changes = ?")
            params.append(int(has_local_changes))
        if is_used_by_project is not None:
            clauses.append("layers.is_used_by_project = ?")
            params.append(int(is_used_by_project))

        where_clause = ""
        if clauses:
            where_clause = f"WHERE {' AND '.join(clauses)}"

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                SELECT layers.resource_id, layers.container_entry_id,
                       layers.connection_id, layers.instance_uuid,
                       layers.has_local_changes, layers.is_used_by_project,
                       layers.last_sync_state, entries.relative_path
                FROM layer_entries AS layers
                JOIN storage_entries AS entries
                    ON entries.id = layers.container_entry_id
                {where_clause}
                ORDER BY layers.resource_id
                """,
                params,
            )
            rows = cursor.fetchall()
        return [self._layer_entry_from_row(row) for row in rows]

    def layer_entry_by_relative_path(
        self,
        relative_path: Path,
    ) -> Optional[Dict[str, object]]:
        """Return a detached layer entry for an indexed relative path."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT layers.resource_id, layers.container_entry_id,
                       layers.connection_id, layers.instance_uuid,
                       layers.has_local_changes, layers.is_used_by_project,
                       layers.last_sync_state, entries.relative_path
                FROM layer_entries AS layers
                JOIN storage_entries AS entries
                    ON entries.id = layers.container_entry_id
                WHERE entries.relative_path = ?
                LIMIT 1
                """,
                (relative_path.as_posix(),),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return self._layer_entry_from_row(row)

    def upsert_attachment_record(
        self,
        attachment_key: AttachmentKey,
        *,
        committed_blob_entry_id: Optional[int],
        staged_blob_entry_id: Optional[int],
        active_blob_entry_id: Optional[int],
        preview_entry_id: Optional[int],
        pending_operation: AttachmentOperation,
        is_deleted_locally: bool = False,
        is_deleted_remotely: bool = False,
    ) -> int:
        """Add or update an attachment record."""
        self._ensure_initialized()
        existing_record = self.attachment_record(attachment_key)
        now = utc_now_text()
        try:
            with self._transaction() as connection:
                if existing_record is None:
                    cursor = connection.execute(
                        """
                        INSERT INTO attachment_records (
                            instance_uuid, resource_id, feature_local_id,
                            feature_ngw_fid, local_attachment_id, ngw_aid,
                            committed_blob_entry_id, staged_blob_entry_id,
                            active_blob_entry_id, preview_entry_id,
                            pending_operation, is_deleted_locally,
                            is_deleted_remotely, created_at, updated_at
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            attachment_key.instance_uuid,
                            attachment_key.resource_id,
                            attachment_key.feature_local_id,
                            attachment_key.feature_ngw_fid,
                            attachment_key.local_attachment_id,
                            attachment_key.ngw_aid,
                            committed_blob_entry_id,
                            staged_blob_entry_id,
                            active_blob_entry_id,
                            preview_entry_id,
                            pending_operation.value,
                            int(is_deleted_locally),
                            int(is_deleted_remotely),
                            now,
                            now,
                        ),
                    )
                    return int(cursor.lastrowid)

                record_id = int(existing_record["id"])
                connection.execute(
                    """
                    UPDATE attachment_records
                    SET committed_blob_entry_id = ?,
                        staged_blob_entry_id = ?,
                        active_blob_entry_id = ?,
                        preview_entry_id = ?,
                        pending_operation = ?,
                        is_deleted_locally = ?,
                        is_deleted_remotely = ?,
                        updated_at = ?,
                        ngw_aid = COALESCE(?, ngw_aid),
                        local_attachment_id = COALESCE(
                            ?,
                            local_attachment_id
                        )
                    WHERE id = ?
                    """,
                    (
                        committed_blob_entry_id,
                        staged_blob_entry_id,
                        active_blob_entry_id,
                        preview_entry_id,
                        pending_operation.value,
                        int(is_deleted_locally),
                        int(is_deleted_remotely),
                        now,
                        attachment_key.ngw_aid,
                        attachment_key.local_attachment_id,
                        record_id,
                    ),
                )
                return record_id
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not upsert attachment record",
                instance_uuid=attachment_key.instance_uuid,
                resource_id=attachment_key.resource_id,
            ) from error

    def attachment_record(
        self,
        attachment_key: AttachmentKey,
    ) -> Optional[Dict[str, object]]:
        """Return an attachment record."""
        self._ensure_initialized()
        clauses = [
            "instance_uuid = ?",
            "resource_id = ?",
            "feature_local_id IS ?",
            "feature_ngw_fid IS ?",
        ]
        params: List[object] = [
            attachment_key.instance_uuid,
            attachment_key.resource_id,
            attachment_key.feature_local_id,
            attachment_key.feature_ngw_fid,
        ]

        if attachment_key.local_attachment_id is not None:
            clauses.append("local_attachment_id = ?")
            params.append(attachment_key.local_attachment_id)
        elif attachment_key.ngw_aid is not None:
            clauses.append("ngw_aid = ?")
            params.append(attachment_key.ngw_aid)
        else:
            clauses.append("local_attachment_id IS NULL")
            clauses.append("ngw_aid IS NULL")

        with self._connect() as connection:
            cursor = connection.execute(
                f"""
                SELECT id, instance_uuid, resource_id, feature_local_id,
                       feature_ngw_fid, local_attachment_id, ngw_aid,
                       committed_blob_entry_id, staged_blob_entry_id,
                       active_blob_entry_id, preview_entry_id,
                       pending_operation, is_deleted_locally,
                       is_deleted_remotely
                FROM attachment_records
                WHERE {" AND ".join(clauses)}
                ORDER BY id
                LIMIT 1
                """,
                params,
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return self._attachment_record_from_row(row)

    def _attachment_record_from_row(
        self,
        row: Sequence[object],
    ) -> Dict[str, object]:
        """Create an attachment record mapping from a SQLite row."""
        keys = (
            "id",
            "instance_uuid",
            "resource_id",
            "feature_local_id",
            "feature_ngw_fid",
            "local_attachment_id",
            "ngw_aid",
            "committed_blob_entry_id",
            "staged_blob_entry_id",
            "active_blob_entry_id",
            "preview_entry_id",
            "pending_operation",
            "is_deleted_locally",
            "is_deleted_remotely",
        )
        result = dict(zip(keys, row))
        result["is_deleted_locally"] = bool(result["is_deleted_locally"])
        result["is_deleted_remotely"] = bool(result["is_deleted_remotely"])
        return result

    def delete_attachment_record(
        self,
        attachment_key: AttachmentKey,
    ) -> None:
        """Delete one logical attachment record."""
        existing_record = self.attachment_record(attachment_key)
        if existing_record is None:
            return

        try:
            with self._transaction() as connection:
                connection.execute(
                    "DELETE FROM attachment_records WHERE id = ?",
                    (int(existing_record["id"]),),
                )
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not delete attachment record",
                instance_uuid=attachment_key.instance_uuid,
                resource_id=attachment_key.resource_id,
            ) from error

    def upsert_blob_remote_map(
        self,
        *,
        blob_entry_id: int,
        fileobj: Optional[object],
        ngw_aid: Optional[int],
        sha256: Optional[str],
        mime_type: Optional[str],
        original_name: Optional[str],
    ) -> None:
        """Add or update a remote blob mapping."""
        self._ensure_initialized()
        try:
            with self._transaction() as connection:
                connection.execute(
                    """
                    INSERT INTO blob_remote_map (
                        blob_entry_id, fileobj, ngw_aid, sha256, mime_type,
                        original_name
                    )
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(blob_entry_id) DO UPDATE SET
                        fileobj = excluded.fileobj,
                        ngw_aid = excluded.ngw_aid,
                        sha256 = excluded.sha256,
                        mime_type = excluded.mime_type,
                        original_name = excluded.original_name
                    """,
                    (
                        blob_entry_id,
                        None if fileobj is None else str(fileobj),
                        ngw_aid,
                        sha256,
                        mime_type,
                        original_name,
                    ),
                )
        except sqlite3.DatabaseError as error:
            raise StorageIndexError(
                "Could not upsert remote blob map",
                blob_entry_id=blob_entry_id,
            ) from error

    def referenced_entry_ids(self) -> Set[int]:
        """Return entry identifiers referenced by attachment records."""
        self._ensure_initialized()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                SELECT committed_blob_entry_id, staged_blob_entry_id,
                       active_blob_entry_id, preview_entry_id
                FROM attachment_records
                """
            )
            rows = cursor.fetchall()

        result: Set[int] = set()
        for row in rows:
            result.update(int(value) for value in row if value is not None)
        return result

    def _gc_reference_filter(
        self,
        delete_referenced_attachments: bool,
    ) -> str:
        """Return SQL that protects attachment references during cleanup."""
        reference_exists = """
                  SELECT 1
                  FROM attachment_records AS records
                  WHERE (
                      records.committed_blob_entry_id = entries.id
                      OR records.staged_blob_entry_id = entries.id
                      OR records.active_blob_entry_id = entries.id
                      OR records.preview_entry_id = entries.id
                  )
        """
        if not delete_referenced_attachments:
            return f"""
                  AND NOT EXISTS (
                      {reference_exists}
                  )
            """

        return f"""
                  AND (
                      (
                          entries.kind IN (?, ?)
                          AND NOT EXISTS (
                              {reference_exists}
                              AND records.pending_operation <> ?
                          )
                      )
                      OR NOT EXISTS (
                          {reference_exists}
                      )
                  )
        """

    def _ensure_initialized(self) -> None:
        """Initialize schema on first use."""
        if self._is_initialized:
            return
        self.initialize()

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        """Open a transaction-bound SQLite connection."""
        with self._connect() as connection:
            try:
                yield connection
                connection.commit()
            except Exception:
                connection.rollback()
                raise

    def _connect(self) -> sqlite3.Connection:
        """Open a SQLite connection."""
        connection = sqlite3.connect(str(self._index_path))
        connection.execute("PRAGMA busy_timeout = 5000")
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _entry_values(
        self,
        entry: StorageEntry,
        now: str,
    ) -> Sequence[object]:
        """Return SQLite values for a storage entry."""
        return (
            entry.storage_key.seed,
            entry.kind.value,
            entry.relative_path.as_posix(),
            entry.instance_uuid,
            entry.resource_id,
            entry.size_bytes,
            entry.sha256,
            entry.state.value,
            entry.protection.value,
            now,
            now,
        )

    def _entry_from_row(self, row: Sequence[object]) -> StorageEntry:
        """Create a storage entry from a SQLite row."""
        storage_key_seed = str(row[1])
        storage_key = StorageKey(
            seed=storage_key_seed,
            instance_uuid=str(row[4]),
            digest=hashlib.sha256(
                storage_key_seed.encode("utf-8")
            ).hexdigest(),
        )
        return StorageEntry(
            id=int(row[0]),
            storage_key=storage_key,
            kind=StorageEntryKind(str(row[2])),
            relative_path=Path(str(row[3])),
            instance_uuid=str(row[4]),
            resource_id=None if row[5] is None else int(row[5]),
            size_bytes=int(row[6]),
            sha256=None if row[7] is None else str(row[7]),
            state=StorageEntryState(str(row[8])),
            protection=StorageEntryProtection(str(row[9])),
        )

    def _layer_entry_from_row(
        self,
        row: Sequence[object],
    ) -> Dict[str, object]:
        """Create a layer entry mapping from a SQLite row."""
        result = {
            "resource_id": int(row[0]),
            "container_entry_id": int(row[1]),
            "connection_id": row[2],
            "instance_uuid": str(row[3]),
            "has_local_changes": bool(row[4]),
            "is_used_by_project": bool(row[5]),
            "last_sync_state": row[6],
        }
        if len(row) > 7:
            result["relative_path"] = Path(str(row[7]))
        return result
