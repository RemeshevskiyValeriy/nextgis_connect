import shutil
from pathlib import Path
from typing import Optional, Union

from qgis.PyQt.QtCore import QMimeDatabase

from nextgis_connect.features.synchronization.infrastructure.storage.attachment_store import (
    AttachmentStore,
)
from nextgis_connect.features.synchronization.infrastructure.storage.detached_layer_store import (
    DetachedLayerStore,
)
from nextgis_connect.features.synchronization.infrastructure.storage.legacy_cache_migrator import (
    LegacyCacheMigrator,
)
from nextgis_connect.features.synchronization.infrastructure.storage.storage_cleanup_service import (
    StorageCleanupService,
)
from nextgis_connect.legacy.detached_editing.utils import container_metadata
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    LayerKey,
    StorageEntryProtection,
    StorageEntryState,
    StorageKey,
)
from nextgis_connect.shared.types import FileObjectId, UnsetType


class DetachedStorageService:
    """Compose detached storage services."""

    def __init__(self, cache_root: Path) -> None:
        """Initialize detached storage service."""
        self._cache_root = Path(cache_root)
        self.detached_layers = DetachedLayerStore(self._cache_root)
        self.attachments = AttachmentStore(self._cache_root)
        self.migrator = LegacyCacheMigrator(self._cache_root)
        self.cleanup = StorageCleanupService(self._cache_root)

    @property
    def cache_root(self) -> Path:
        """Return the cache root path."""
        return self._cache_root

    def container_path(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
    ) -> Path:
        """Return the canonical detached container path."""
        return self.detached_layers.container_path(
            LayerKey(instance_uuid, int(resource_id))
        )

    def ensure_container_placeholder(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        *,
        connection_id: Optional[str] = None,
    ) -> Path:
        """Ensure an index placeholder for a detached container path."""
        layer_key = LayerKey(instance_uuid, int(resource_id))
        self.detached_layers.ensure_container_placeholder(
            layer_key,
            connection_id=connection_id,
        )
        return self.detached_layers.container_path(layer_key)

    def canonical_container_path(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        *,
        connection_id: Optional[str] = None,
        source_container_path: Optional[Path] = None,
    ) -> Optional[Path]:
        """Return the canonical container path and move cache sources if needed."""
        canonical_container_path = self.container_path(
            instance_uuid,
            resource_id,
        )
        if source_container_path is None:
            return canonical_container_path

        source_container_path = Path(source_container_path)
        if source_container_path == canonical_container_path:
            return canonical_container_path

        if not source_container_path.exists():
            return canonical_container_path

        if not self._is_cache_path(source_container_path):
            logger.warning(
                "Detached container source is outside cache and will not be "
                f"moved: {source_container_path}"
            )
            return canonical_container_path

        if canonical_container_path.exists():
            logger.warning(
                "Detached container canonical cache path already exists: "
                f"{canonical_container_path}"
            )
            return canonical_container_path

        try:
            if not self.register_detached_container(
                instance_uuid,
                resource_id,
                connection_id=connection_id,
                container_path=source_container_path,
            ):
                return None
            self._move_detached_container_service_files(
                source_container_path,
                canonical_container_path,
            )
            source_container_path.unlink(missing_ok=True)
            self._remove_empty_dirs(source_container_path.parent)
        except Exception:
            logger.exception("Could not move detached container")
            return None

        return canonical_container_path

    def register_detached_container(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        *,
        connection_id: Optional[str] = None,
        container_path: Optional[Path] = None,
        is_used_by_project: bool = False,
    ) -> bool:
        """Register an existing detached container in the storage index."""
        layer_key = LayerKey(instance_uuid, int(resource_id))
        canonical_container_path = self.container_path(
            instance_uuid,
            resource_id,
        )
        container_path = container_path or canonical_container_path
        if not container_path.exists():
            return False

        try:
            metadata = container_metadata(container_path)
        except Exception:
            return False

        self.detached_layers.ensure_container_entry(
            layer_key,
            None
            if container_path == canonical_container_path
            else container_path,
            connection_id=connection_id or metadata.connection_id,
            has_local_changes=metadata.has_changes,
            is_used_by_project=is_used_by_project,
        )
        return True

    def attachment_directory(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
    ) -> Path:
        """Return the canonical attachment blob directory."""
        storage_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        return self.attachments.blob_path(storage_key).parent

    def attachment_path(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        file_name: Optional[str] = None,
        mime_type: Optional[str] = None,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
    ) -> Path:
        """Return the canonical attachment blob path."""
        attachment_directory = self.attachment_directory(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        extension = self._guess_extension(
            file_name=file_name,
            mime_type=mime_type,
        )
        file_name = f"blob{extension}" if extension else "blob"
        return attachment_directory / file_name

    def attachment_thumbnail_directory(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
    ) -> Path:
        """Return the canonical attachment thumbnail directory."""
        blob_storage_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        return self.attachments.preview_path(blob_storage_key).parent

    def attachment_thumbnail_path(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
    ) -> Path:
        """Return the canonical attachment thumbnail path."""
        return (
            self.attachment_thumbnail_directory(
                instance_uuid,
                resource_id,
                attachment_id,
                fileobj=fileobj,
            )
            / "preview.jpg"
        )

    def register_attachment_file(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        file_name: Optional[str] = None,
        mime_type: Optional[str] = None,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
        feature_local_id: Optional[int] = None,
        feature_ngw_fid: Optional[int] = None,
        ngw_aid: Optional[int] = None,
        is_dirty: bool = False,
    ) -> bool:
        """Register an existing attachment file in the storage index."""
        path = self.attachment_path(
            instance_uuid,
            resource_id,
            attachment_id,
            file_name=file_name,
            mime_type=mime_type,
            fileobj=fileobj,
        )
        if not path.exists():
            return False

        storage_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        has_fileobj = bool(fileobj) and fileobj != -1
        state = (
            StorageEntryState.COMMITTED
            if has_fileobj
            else StorageEntryState.STAGED
        )
        protection = (
            StorageEntryProtection.DIRTY
            if is_dirty or not has_fileobj
            else StorageEntryProtection.NONE
        )
        pending_operation = (
            AttachmentOperation.NONE
            if has_fileobj
            else AttachmentOperation.CREATE
        )
        entry = self.attachments.register_blob_file(
            self._attachment_key(
                instance_uuid,
                resource_id,
                attachment_id,
                feature_local_id=feature_local_id,
                feature_ngw_fid=feature_ngw_fid,
                ngw_aid=ngw_aid,
            ),
            storage_key,
            path.name,
            state=state,
            protection=protection,
            pending_operation=pending_operation,
            fileobj=fileobj if has_fileobj else None,
            ngw_aid=ngw_aid,
            mime_type=mime_type,
            original_name=file_name,
        )
        return entry is not None

    def register_attachment_thumbnail(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
        feature_local_id: Optional[int] = None,
        feature_ngw_fid: Optional[int] = None,
        ngw_aid: Optional[int] = None,
    ) -> bool:
        """Register an existing attachment thumbnail in the storage index."""
        path = self.attachment_thumbnail_path(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        if not path.exists():
            return False

        blob_storage_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        entry = self.attachments.register_preview_file(
            self._attachment_key(
                instance_uuid,
                resource_id,
                attachment_id,
                feature_local_id=feature_local_id,
                feature_ngw_fid=feature_ngw_fid,
                ngw_aid=ngw_aid,
            ),
            blob_storage_key,
        )
        return entry is not None

    def remove_attachment_cache(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
    ) -> None:
        """Remove cached attachment blob and thumbnail files."""
        blob_storage_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=fileobj,
        )
        preview_storage_key = self.attachments.preview_key(blob_storage_key)
        storage_index = self.attachments.index_for_instance(instance_uuid)

        for storage_key in (blob_storage_key, preview_storage_key):
            entry = storage_index.find_entry(storage_key)
            if entry is not None and entry.id is not None:
                storage_index.delete_entry(entry.id)

        for path in (
            self.attachment_directory(
                instance_uuid,
                resource_id,
                attachment_id,
                fileobj=fileobj,
            ),
            self.attachment_thumbnail_directory(
                instance_uuid,
                resource_id,
                attachment_id,
                fileobj=fileobj,
            ),
        ):
            if path.exists():
                shutil.rmtree(path)

    def move_attachment_cache_to_fileobj(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        old_fileobj: Union[UnsetType, None, FileObjectId],
        new_fileobj: FileObjectId,
    ) -> None:
        """Move cached attachment files to a remote file object key."""
        if old_fileobj == new_fileobj:
            return

        old_blob_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=old_fileobj,
        )
        new_blob_key = self._attachment_blob_key(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=new_fileobj,
        )
        old_blob_directory = self.attachment_directory(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=old_fileobj,
        )
        new_blob_directory = self.attachment_directory(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=new_fileobj,
        )
        self._move_cache_directory(old_blob_directory, new_blob_directory)

        old_thumbnail_directory = self.attachment_thumbnail_directory(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=old_fileobj,
        )
        new_thumbnail_directory = self.attachment_thumbnail_directory(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=new_fileobj,
        )
        self._move_cache_directory(
            old_thumbnail_directory,
            new_thumbnail_directory,
        )

        storage_index = self.attachments.index_for_instance(instance_uuid)
        for storage_key in (
            old_blob_key,
            self.attachments.preview_key(old_blob_key),
        ):
            entry = storage_index.find_entry(storage_key)
            if entry is not None and entry.id is not None:
                storage_index.delete_entry(entry.id)

        ngw_aid = int(attachment_id) if str(attachment_id).isdigit() else None
        if new_blob_directory.exists():
            for blob_path in new_blob_directory.iterdir():
                if not blob_path.is_file():
                    continue

                self.attachments.register_blob_file(
                    self._attachment_key(
                        instance_uuid,
                        resource_id,
                        attachment_id,
                        ngw_aid=ngw_aid,
                    ),
                    new_blob_key,
                    blob_path.name,
                    state=StorageEntryState.COMMITTED,
                    protection=StorageEntryProtection.NONE,
                    pending_operation=AttachmentOperation.NONE,
                    fileobj=new_fileobj,
                    ngw_aid=ngw_aid,
                )

        self.register_attachment_thumbnail(
            instance_uuid,
            resource_id,
            attachment_id,
            fileobj=new_fileobj,
            ngw_aid=ngw_aid,
        )

    def _attachment_key(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        feature_local_id: Optional[int] = None,
        feature_ngw_fid: Optional[int] = None,
        ngw_aid: Optional[int] = None,
    ) -> AttachmentKey:
        """Return a logical attachment key."""
        return AttachmentKey(
            instance_uuid=instance_uuid,
            resource_id=int(resource_id),
            feature_local_id=feature_local_id,
            feature_ngw_fid=feature_ngw_fid,
            local_attachment_id=str(attachment_id),
            ngw_aid=ngw_aid,
        )

    def _attachment_blob_key(
        self,
        instance_uuid: str,
        resource_id: Union[int, str],
        attachment_id: Union[int, str],
        *,
        fileobj: Union[UnsetType, None, FileObjectId] = None,
    ) -> StorageKey:
        """Return the physical attachment blob key."""
        if bool(fileobj) and fileobj != -1:
            return self.attachments.remote_blob_key(
                instance_uuid,
                int(resource_id),
                fileobj,
            )

        return self.attachments.local_blob_key(
            instance_uuid,
            int(resource_id),
            str(attachment_id),
        )

    def _move_cache_directory(
        self,
        source_directory: Path,
        target_directory: Path,
    ) -> None:
        """Move directory contents into another cache directory."""
        if not source_directory.exists():
            return

        target_directory.mkdir(parents=True, exist_ok=True)
        for source_path in source_directory.iterdir():
            source_path.rename(target_directory / source_path.name)
        source_directory.rmdir()

    def _move_detached_container_service_files(
        self,
        source_container_path: Path,
        target_container_path: Path,
    ) -> None:
        """Move GeoPackage service files next to the canonical container."""
        for service_file in source_container_path.parent.glob(
            f"{source_container_path.name}-*"
        ):
            suffix = service_file.name[len(source_container_path.name) :]
            target_file = target_container_path.parent / (
                target_container_path.name + suffix
            )
            if target_file.exists():
                continue
            service_file.replace(target_file)

    def _remove_empty_dirs(self, path: Path) -> None:
        """Remove empty directories below the cache root."""
        current_path = Path(path)
        while current_path != self._cache_root:
            try:
                current_path.rmdir()
            except OSError:
                return
            current_path = current_path.parent

    def _is_cache_path(self, file_path: Path) -> bool:
        """Return whether a file belongs to this cache root."""
        try:
            file_path.resolve().relative_to(self._cache_root.resolve())
        except ValueError:
            return False
        return True

    def _guess_extension(
        self,
        *,
        file_name: Optional[str],
        mime_type: Optional[str],
    ) -> str:
        """Return an extension for an attachment file."""
        if file_name is not None:
            extension = Path(file_name).suffix
            if extension:
                return extension

        if mime_type is None:
            return ""

        mime_type_database = QMimeDatabase()
        mime = mime_type_database.mimeTypeForName(mime_type)
        extension = mime.preferredSuffix()
        if not extension:
            return ""
        return f".{extension}"
