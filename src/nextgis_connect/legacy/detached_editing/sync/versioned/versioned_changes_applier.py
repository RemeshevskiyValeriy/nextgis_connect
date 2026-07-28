from typing import Any, List, Optional, Sequence, Tuple, Union, cast

from nextgis_connect.features.synchronization.infrastructure.storage import (
    DetachedStorageService,
)
from nextgis_connect.legacy.detached_editing.storage_service_factory import (
    DetachedStorageServiceFactory,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes import (
    AttachmentCreation,
    AttachmentDeletion,
    AttachmentRestoration,
    AttachmentUpdate,
    DescriptionPut,
    FeatureChange,
    FeatureCreation,
    FeatureDeletion,
    FeatureRestoration,
    FeatureUpdate,
)
from nextgis_connect.legacy.detached_editing.sync.common.changes_applier import (
    ChangesApplier,
)
from nextgis_connect.legacy.detached_editing.utils import (
    AttachmentMetadata,
    DetachedContainerContext,
    FeatureMetadata,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.errors import (
    ContainerError,
    SynchronizationError,
)
from nextgis_connect.shared.types import AttachmentId, FileObjectId, Unset


class VersionedChangesApplier(ChangesApplier):
    def __init__(self, container_context: DetachedContainerContext) -> None:
        super().__init__(container_context)
        if not container_context.metadata.is_versioning_enabled:
            raise ContainerError("Container does not have versioning enabled")

    def apply(
        self,
        changes: Union[FeatureChange, Sequence[FeatureChange]],
        operation_result: Any = None,
    ) -> None:
        changes_list = changes
        if not isinstance(changes, (list, tuple)):
            changes_list = [changes]

        changes_list = cast(Sequence[FeatureChange], changes_list)

        if len(changes_list) == 0:
            return

        operation_result = cast(Sequence, operation_result)
        if not operation_result:
            raise SynchronizationError("Empty operation result")

        if len(changes_list) != len(operation_result):
            raise SynchronizationError("Result length is not equal")

        self.__apply(changes_list, operation_result)

    def __apply(
        self,
        changes: Sequence[FeatureChange],
        operation_result: Sequence,
    ) -> None:
        added_features: List[FeatureMetadata] = []
        updated_features: List[FeatureUpdate] = []
        delete_changes: List[FeatureDeletion] = []
        restore_changes: List[FeatureRestoration] = []

        updated_descriptions: List[DescriptionPut] = []

        added_attachments: List[AttachmentMetadata] = []
        updated_attachments: List[AttachmentMetadata] = []
        deleted_attachments: List[AttachmentDeletion] = []
        restored_attachments: List[AttachmentMetadata] = []

        uploaded_files: List[Tuple[AttachmentId, FileObjectId]] = []

        for change, (_, change_result) in zip(changes, operation_result):
            if isinstance(change, FeatureCreation):
                added_features.append(
                    FeatureMetadata(
                        fid=change.fid, ngw_fid=change_result["fid"]
                    )
                )

            elif isinstance(change, FeatureDeletion):
                delete_changes.append(change)

            elif isinstance(change, FeatureRestoration):
                restore_changes.append(change)

            elif isinstance(change, FeatureUpdate):
                updated_features.append(change)

            elif isinstance(change, DescriptionPut):
                updated_descriptions.append(change)

            elif isinstance(change, AttachmentCreation):
                added_attachments.append(
                    AttachmentMetadata(
                        fid=change.fid,
                        aid=change.aid,
                        ngw_aid=change_result["aid"],
                        fileobj=change_result["fileobj"],
                    )
                )
                uploaded_files.append((change.aid, change_result["fileobj"]))

            elif isinstance(change, AttachmentUpdate):
                updated_attachments.append(
                    AttachmentMetadata(
                        fid=change.fid,
                        aid=change.aid,
                        ngw_fid=change.ngw_fid,
                        ngw_aid=change.ngw_aid,
                        fileobj=change_result["fileobj"]
                        if change.is_file_new
                        else Unset,
                    )
                )
                if change.is_file_new:
                    uploaded_files.append(
                        (change.aid, change_result["fileobj"])
                    )

            elif isinstance(change, AttachmentDeletion):
                deleted_attachments.append(change)

            elif isinstance(change, AttachmentRestoration):
                restored_attachments.append(
                    AttachmentMetadata(
                        fid=change.fid,
                        aid=change.aid,
                        ngw_fid=change.ngw_fid,
                        ngw_aid=change.ngw_aid,
                        fileobj=change_result["fileobj"]
                        if change.is_file_new
                        else Unset,
                    )
                )
                if change.is_file_new:
                    uploaded_files.append(
                        (change.aid, change_result["fileobj"])
                    )

        self._process_added_features(added_features)
        self._process_updated_features(updated_features)
        self._process_deleted_features(delete_changes)
        self._process_restored_features(restore_changes)

        self._process_updated_descriptions(updated_descriptions)
        self._process_created_attachments(added_attachments)
        self._process_updated_attachments(updated_attachments)
        self._process_deleted_attachments(deleted_attachments)
        self._process_restored_attachments(restored_attachments)

        self.__move_cache_if_needed(uploaded_files)

    def __move_cache_if_needed(
        self,
        attachments_info: Sequence[Tuple[AttachmentId, FileObjectId]],
    ) -> None:
        if len(attachments_info) == 0:
            return

        storage_service = DetachedStorageServiceFactory.create()
        for attachment_id, new_fileobj in attachments_info:
            self.__move_attachment_cache(
                storage_service,
                attachment_id,
                old_fileobj=None,
                new_fileobj=new_fileobj,
            )

    def __move_attachment_cache(
        self,
        storage_service: DetachedStorageService,
        attachment_id: AttachmentId,
        *,
        old_fileobj: Optional[FileObjectId],
        new_fileobj: FileObjectId,
    ) -> None:
        if old_fileobj == new_fileobj:
            return

        positional_arguments = (
            self._context.metadata.instance_id,
            self._context.metadata.resource_id,
            attachment_id,
        )

        logger.debug(
            "Moving attachment cache for aid %s to fileobj %s",
            attachment_id,
            new_fileobj,
        )
        storage_service.move_attachment_cache_to_fileobj(
            *positional_arguments,
            old_fileobj=old_fileobj,
            new_fileobj=new_fileobj,
        )
