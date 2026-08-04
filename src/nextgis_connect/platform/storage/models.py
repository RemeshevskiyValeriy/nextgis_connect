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

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional


class StorageEntryKind(Enum):
    """Enumerate indexed storage entry kinds."""

    LAYER_CONTAINER = "layer_container"
    ATTACHMENT_BLOB = "attachment_blob"
    ATTACHMENT_PREVIEW = "attachment_preview"
    TEMPORARY_FILE = "temporary_file"
    SERVICE_FILE = "service_file"
    UNKNOWN_LEGACY_FILE = "unknown_legacy_file"


class StorageEntryState(Enum):
    """Enumerate indexed storage entry states."""

    COMMITTED = "committed"
    STAGED = "staged"
    UPLOADED_PENDING_COMMIT = "uploaded_pending_commit"
    ORPHANED = "orphaned"
    GC_CANDIDATE = "gc_candidate"
    TEMPORARY = "temporary"
    QUARANTINED = "quarantined"


class StorageEntryProtection(Enum):
    """Enumerate storage entry protection states."""

    NONE = "none"
    DIRTY = "dirty"
    USED_BY_PROJECT = "used_by_project"
    LEASED = "leased"
    RETAIN_FOR_ROLLBACK = "retain_for_rollback"


class AttachmentOperation(Enum):
    """Enumerate pending attachment operations."""

    NONE = "none"
    CREATE = "create"
    UPDATE_FILE = "update_file"
    UPDATE_METADATA = "update_metadata"
    DELETE = "delete"
    DELETE_DUE_TO_FEATURE_DELETE = "delete_due_to_feature_delete"
    RESTORE = "restore"


@dataclass(frozen=True)
class StorageKey:
    """Represent a canonical storage key."""

    seed: str
    instance_uuid: str
    digest: str

    def __str__(self) -> str:
        """Return the canonical seed."""
        return self.seed


@dataclass(frozen=True)
class LayerKey:
    """Identify a detached layer container."""

    instance_uuid: str
    resource_id: int


@dataclass(frozen=True)
class AttachmentKey:
    """Identify a logical attachment record."""

    instance_uuid: str
    resource_id: int
    feature_local_id: Optional[int]
    feature_ngw_fid: Optional[int]
    local_attachment_id: Optional[str]
    ngw_aid: Optional[int]


@dataclass(frozen=True)
class BlobRef:
    """Reference a concrete blob in storage."""

    storage_key: StorageKey
    entry_id: Optional[int]
    path: Path


@dataclass(frozen=True)
class StorageEntry:
    """Represent one indexed physical storage file."""

    id: Optional[int]
    storage_key: StorageKey
    kind: StorageEntryKind
    relative_path: Path
    instance_uuid: str
    resource_id: Optional[int]
    size_bytes: int
    sha256: Optional[str]
    state: StorageEntryState
    protection: StorageEntryProtection
