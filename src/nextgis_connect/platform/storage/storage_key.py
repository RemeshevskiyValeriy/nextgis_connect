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
import uuid
from typing import Optional

from nextgis_connect.platform.storage.models import LayerKey, StorageKey


class StorageKeyFactory:
    """Create canonical storage keys."""

    @staticmethod
    def layer_container(layer_key: LayerKey) -> StorageKey:
        """Create a detached layer container key."""
        seed = (
            "layer-container:v1:"
            f"{layer_key.instance_uuid}:{layer_key.resource_id}"
        )
        return StorageKeyFactory._from_seed(seed, layer_key.instance_uuid)

    @staticmethod
    def remote_attachment_blob(
        instance_uuid: str,
        resource_id: int,
        fileobj: object,
    ) -> StorageKey:
        """Create a remote attachment blob key."""
        seed = (
            "attachment-blob-remote:v1:"
            f"{instance_uuid}:{resource_id}:fileobj:{fileobj}"
        )
        return StorageKeyFactory._from_seed(seed, instance_uuid)

    @staticmethod
    def local_attachment_blob(
        instance_uuid: str,
        resource_id: int,
        local_blob_uuid: str,
    ) -> StorageKey:
        """Create a local staged attachment blob key."""
        seed = (
            "attachment-blob-local:v1:"
            f"{instance_uuid}:{resource_id}:local:{local_blob_uuid}"
        )
        return StorageKeyFactory._from_seed(seed, instance_uuid)

    @staticmethod
    def attachment_preview(
        blob_storage_key: StorageKey,
        preview_profile: str,
    ) -> StorageKey:
        """Create an attachment preview key."""
        seed = (
            "attachment-preview:v1:"
            f"{blob_storage_key.seed}:jpg:{preview_profile}"
        )
        return StorageKeyFactory._from_seed(
            seed,
            blob_storage_key.instance_uuid,
        )

    @staticmethod
    def temporary_file(
        instance_uuid: str,
        operation_uuid: str,
        purpose: str,
    ) -> StorageKey:
        """Create a temporary file key."""
        seed = f"temp:v1:{instance_uuid}:{operation_uuid}:{purpose}"
        return StorageKeyFactory._from_seed(seed, instance_uuid)

    @staticmethod
    def migration_local_blob_uuid(
        instance_uuid: str,
        resource_id: int,
        attachment_id: object,
    ) -> str:
        """Create a deterministic local blob UUID for migration."""
        seed = f"{instance_uuid}:{resource_id}:{attachment_id}"
        return str(uuid.uuid5(uuid.NAMESPACE_URL, seed))

    @staticmethod
    def _from_seed(seed: str, instance_uuid: str) -> StorageKey:
        """Create a storage key from a seed."""
        digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
        return StorageKey(
            seed=seed, instance_uuid=instance_uuid, digest=digest
        )


def safe_blob_file_name(extension: Optional[str] = None) -> str:
    """Return a stable attachment blob file name."""
    if not extension:
        return "blob"

    normalized_extension = extension.lower().strip()
    if not normalized_extension:
        return "blob"

    if not normalized_extension.startswith("."):
        normalized_extension = f".{normalized_extension}"

    if (
        not normalized_extension[1:]
        .replace("-", "")
        .replace("_", "")
        .isalnum()
    ):
        return "blob"

    return f"blob{normalized_extension}"
