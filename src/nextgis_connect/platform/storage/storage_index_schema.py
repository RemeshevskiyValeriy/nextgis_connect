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

import sqlite3
from datetime import datetime, timezone

SCHEMA_VERSION = 1


def utc_now_text() -> str:
    """Return current UTC time as an ISO string."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def initialize_schema(connection: sqlite3.Connection) -> None:
    """Initialize the storage index schema."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS storage_schema (
            version INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS storage_entries (
            id INTEGER PRIMARY KEY,
            storage_key TEXT NOT NULL UNIQUE,
            kind TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            instance_uuid TEXT NOT NULL,
            resource_id INTEGER,
            size_bytes INTEGER NOT NULL DEFAULT 0,
            sha256 TEXT,
            state TEXT NOT NULL,
            protection TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_accessed_at TEXT,
            last_checked_at TEXT
        );

        CREATE TABLE IF NOT EXISTS layer_entries (
            resource_id INTEGER NOT NULL,
            container_entry_id INTEGER NOT NULL,
            connection_id TEXT,
            instance_uuid TEXT NOT NULL,
            has_local_changes INTEGER NOT NULL DEFAULT 0,
            is_used_by_project INTEGER NOT NULL DEFAULT 0,
            last_sync_state TEXT,
            PRIMARY KEY (instance_uuid, resource_id),
            UNIQUE (container_entry_id),
            FOREIGN KEY (container_entry_id)
                REFERENCES storage_entries(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS attachment_records (
            id INTEGER PRIMARY KEY,
            instance_uuid TEXT NOT NULL,
            resource_id INTEGER NOT NULL,
            feature_local_id INTEGER,
            feature_ngw_fid INTEGER,
            local_attachment_id TEXT,
            ngw_aid INTEGER,
            committed_blob_entry_id INTEGER,
            staged_blob_entry_id INTEGER,
            active_blob_entry_id INTEGER,
            preview_entry_id INTEGER,
            pending_operation TEXT NOT NULL DEFAULT 'none',
            is_deleted_locally INTEGER NOT NULL DEFAULT 0,
            is_deleted_remotely INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (committed_blob_entry_id)
                REFERENCES storage_entries(id)
                ON DELETE SET NULL,
            FOREIGN KEY (staged_blob_entry_id)
                REFERENCES storage_entries(id)
                ON DELETE SET NULL,
            FOREIGN KEY (active_blob_entry_id)
                REFERENCES storage_entries(id)
                ON DELETE SET NULL,
            FOREIGN KEY (preview_entry_id)
                REFERENCES storage_entries(id)
                ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS blob_remote_map (
            blob_entry_id INTEGER PRIMARY KEY,
            fileobj TEXT,
            ngw_aid INTEGER,
            sha256 TEXT,
            mime_type TEXT,
            original_name TEXT,
            FOREIGN KEY (blob_entry_id)
                REFERENCES storage_entries(id)
                ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS storage_leases (
            id INTEGER PRIMARY KEY,
            entry_id INTEGER NOT NULL,
            owner TEXT NOT NULL,
            operation_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT,
            FOREIGN KEY (entry_id)
                REFERENCES storage_entries(id)
                ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_storage_entries_resource
            ON storage_entries(resource_id);
        CREATE INDEX IF NOT EXISTS idx_storage_entries_instance
            ON storage_entries(instance_uuid);
        CREATE INDEX IF NOT EXISTS idx_storage_entries_instance_resource
            ON storage_entries(instance_uuid, resource_id);
        CREATE UNIQUE INDEX IF NOT EXISTS idx_storage_entries_relative_path
            ON storage_entries(relative_path);
        CREATE INDEX IF NOT EXISTS idx_storage_entries_gc
            ON storage_entries(state, protection);
        CREATE INDEX IF NOT EXISTS idx_attachment_records_resource
            ON attachment_records(instance_uuid, resource_id);
        CREATE INDEX IF NOT EXISTS idx_storage_leases_entry
            ON storage_leases(entry_id);
        CREATE INDEX IF NOT EXISTS idx_storage_leases_operation
            ON storage_leases(operation_id);
        """
    )

    cursor = connection.execute("SELECT version FROM storage_schema LIMIT 1")
    row = cursor.fetchone()
    now = utc_now_text()
    if row is None:
        connection.execute(
            """
            INSERT INTO storage_schema (version, created_at, updated_at)
            VALUES (?, ?, ?)
            """,
            (SCHEMA_VERSION, now, now),
        )
        return

    if int(row[0]) != SCHEMA_VERSION:
        raise sqlite3.DatabaseError(
            f"Unsupported storage schema version: {row[0]}"
        )
