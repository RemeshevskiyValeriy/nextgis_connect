import json
from dataclasses import replace
from enum import Enum, auto
from pathlib import Path
from typing import (
    Any,
    Dict,
    Iterable,
    List,
    Optional,
    Sequence,
    Set,
    Tuple,
    Union,
    cast,
)

from qgis.core import (
    QgsFeature,
    QgsFeatureRequest,
    QgsGeometry,
    QgsVectorLayer,
)

from nextgis_connect.detached_editing.conflicts.conflict_resolution import (
    AttachmentConflictResolution,
    AttachmentResolutionData,
    ConflictResolution,
    DescriptionConflictResolution,
    FeatureConflictResolution,
    FeatureResolutionData,
    ResolutionType,
)
from nextgis_connect.detached_editing.conflicts.conflicts import (
    AttachmentDataConflict,
    DescriptionConflict,
    FeatureDataConflict,
    LocalAttachmentDeletionConflict,
    LocalFeatureDeletionConflict,
    RemoteAttachmentDeletionConflict,
    RemoteFeatureDeletionConflict,
)
from nextgis_connect.detached_editing.container.editing.container_sessions import (
    ContainerReadOnlySession,
    ContainerReadWriteSession,
)
from nextgis_connect.detached_editing.sync.common.changes import (
    AttachmentCreation,
    AttachmentDeletion,
    AttachmentRestoration,
    AttachmentUpdate,
    DescriptionPut,
    FeatureRestoration,
    FeatureUpdate,
)
from nextgis_connect.detached_editing.sync.common.serialization import (
    deserialize_geometry,
    deserialize_value,
    serialize_geometry,
    serialize_value,
    simplify_value,
)
from nextgis_connect.detached_editing.sync.versioned.actions import (
    AttachmentDeleteAction,
    AttachmentRestoreAction,
    AttachmentUpdateAction,
    FeatureDeleteAction,
    VersioningAction,
)
from nextgis_connect.detached_editing.utils import (
    DetachedContainerContext,
    DetachedContainerMetaData,
    detached_layer_uri,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.errors import DetachedEditingError
from nextgis_connect.resources.ngw_field import FieldId
from nextgis_connect.shared.types import (
    AttachmentId,
    FeatureId,
    Unset,
    UnsetType,
)


class ConflictsResolutionApplier:
    _context: DetachedContainerContext
    _container_path: Path
    _metadata: DetachedContainerMetaData
    _remote_actions: List[VersioningAction]

    class Status(Enum):
        NotResolved = auto()
        PartiallyResolved = auto()
        Resolved = auto()

    def __init__(self, context: DetachedContainerContext) -> None:
        self._context = context
        self._container_path = context.path
        self._metadata = context.metadata
        self._remote_actions = []

    def apply(
        self,
        resolutions: Sequence[ConflictResolution],
        remote_actions: Sequence[VersioningAction],
    ) -> Tuple[Status, List[VersioningAction]]:
        try:
            return self._apply(remote_actions, resolutions)
        except Exception as error:
            logger.exception("Resolution failed")
            raise DetachedEditingError from error

    def _apply(
        self,
        remote_actions: Sequence[VersioningAction],
        resolutions: Sequence[ConflictResolution],
    ) -> Tuple[Status, List[VersioningAction]]:
        self._remote_actions = list(remote_actions)
        has_resolved = False

        for resolution in resolutions:
            if resolution.resolution_type == ResolutionType.NoResolution:
                status = (
                    self.Status.PartiallyResolved
                    if has_resolved
                    else self.Status.NotResolved
                )
                return status, []

            has_resolved = True
            self._apply_resolution(resolution)

        return self.Status.Resolved, list(self._remote_actions)

    def _apply_resolution(self, resolution: ConflictResolution) -> None:
        conflict = resolution.conflict

        if isinstance(conflict, FeatureDataConflict):
            assert isinstance(resolution, FeatureConflictResolution)
            self._apply_feature_data_resolution(resolution)
            return

        if isinstance(conflict, DescriptionConflict):
            assert isinstance(resolution, DescriptionConflictResolution)
            self._apply_description_resolution(resolution)
            return

        if isinstance(conflict, AttachmentDataConflict):
            assert isinstance(resolution, AttachmentConflictResolution)
            self._apply_attachment_data_resolution(resolution)
            return

        if isinstance(conflict, LocalFeatureDeletionConflict):
            self._apply_local_feature_delete_resolution(resolution)
            return

        if isinstance(conflict, RemoteFeatureDeletionConflict):
            self._apply_remote_feature_delete_resolution(resolution)
            return

        if isinstance(conflict, LocalAttachmentDeletionConflict):
            self._apply_local_attachment_delete_resolution(resolution)
            return

        if isinstance(conflict, RemoteAttachmentDeletionConflict):
            self._apply_remote_attachment_delete_resolution(resolution)
            return

        raise NotImplementedError

    def _apply_feature_data_resolution(
        self,
        resolution: FeatureConflictResolution,
    ) -> None:
        conflict = cast(FeatureDataConflict, resolution.conflict)
        local_fid = conflict.local_change.fid
        remote_action = conflict.remote_action

        remote_values, remote_geometry = self._remote_feature_state(conflict)
        chosen_values = self._feature_resolution_fields(
            resolution.feature_data
        )
        chosen_geometry = self._resolution_geometry(resolution.feature_data)

        if resolution.resolution_type == ResolutionType.Local:
            self._set_feature_version(local_fid, remote_action.vid)
            remaining_fields = [
                field_data
                for field_data in remote_action.fields_dict.items()
                if field_data[0] not in conflict.conflicting_fields
            ]
            updated_action = replace(
                remote_action,
                fields=remaining_fields,
                geom=Unset
                if conflict.has_geometry_conflict
                else remote_action.geom,
            )
            self._replace_action(remote_action, updated_action)
            if isinstance(conflict.local_change, FeatureRestoration):
                self._delete_restored_feature_marker(local_fid)
            self._upsert_feature_field_markers(
                local_fid,
                {
                    field_id: remote_values[field_id]
                    for field_id in conflict.conflicting_fields
                },
            )
            if conflict.has_geometry_conflict:
                self._upsert_feature_geometry_marker(
                    local_fid,
                    remote_geometry,
                )
            return

        if resolution.resolution_type == ResolutionType.Remote:
            if isinstance(conflict.local_change, FeatureRestoration):
                self._delete_restored_feature_marker(local_fid)
            self._delete_feature_markers(
                local_fid,
                conflict.conflicting_fields,
                conflict.has_geometry_conflict,
            )
            return

        updated_action = replace(
            remote_action,
            fields=list(resolution.feature_data.fields),
            geom=chosen_geometry,
        )
        self._set_feature_version(local_fid, remote_action.vid)
        self._replace_action(remote_action, updated_action)
        if isinstance(conflict.local_change, FeatureRestoration):
            self._delete_restored_feature_marker(local_fid)

        fields_to_keep = {
            field_id: remote_value
            for field_id, remote_value in remote_values.items()
            if chosen_values[field_id] != remote_value
        }
        fields_to_remove = set(remote_values.keys()) - set(
            fields_to_keep.keys()
        )
        self._delete_feature_markers(local_fid, fields_to_remove, False)
        self._upsert_feature_field_markers(local_fid, fields_to_keep)

        if self._geometries_equal(chosen_geometry, remote_geometry):
            self._delete_feature_markers(local_fid, set(), True)
        else:
            self._upsert_feature_geometry_marker(local_fid, remote_geometry)

    def _apply_description_resolution(
        self,
        resolution: DescriptionConflictResolution,
    ) -> None:
        conflict = cast(DescriptionConflict, resolution.conflict)
        local_fid = conflict.local_change.fid
        remote_action = conflict.remote_action

        if resolution.resolution_type == ResolutionType.Remote:
            self._delete_description_marker(local_fid)
            return

        self._set_description_version(local_fid, remote_action.vid)
        updated_action = replace(remote_action, value=resolution.value)
        self._replace_action(remote_action, updated_action)

        if resolution.value == remote_action.value:
            self._delete_description_marker(local_fid)
            return

        self._upsert_description_marker(
            local_fid,
            remote_action.value,
            remote_action.vid,
        )

    def _apply_attachment_data_resolution(
        self,
        resolution: AttachmentConflictResolution,
    ) -> None:
        conflict = cast(AttachmentDataConflict, resolution.conflict)
        local_aid = conflict.local_change.aid
        remote_action = conflict.remote_action
        remote_state = self._remote_attachment_state(conflict)

        if resolution.resolution_type == ResolutionType.Local:
            self._set_attachment_version(local_aid, remote_action.vid)
            updated_action = self._attachment_action_without_conflicts(
                conflict
            )
            self._replace_action(remote_action, updated_action)
            if isinstance(conflict.local_change, AttachmentRestoration):
                self._delete_restored_attachment_marker(local_aid)
            self._upsert_attachment_marker(local_aid, remote_state)
            return

        if resolution.resolution_type == ResolutionType.Remote:
            if isinstance(conflict.local_change, AttachmentRestoration):
                self._delete_restored_attachment_marker(local_aid)
            if self._has_attachment_local_changes_after_remote(conflict):
                self._upsert_attachment_marker(local_aid, remote_state)
            else:
                self._delete_attachment_marker(local_aid)
            return

        updated_action = self._attachment_action_with_resolution(
            remote_action,
            resolution.attachment_data,
        )
        self._set_attachment_version(local_aid, remote_action.vid)
        self._replace_action(remote_action, updated_action)
        if isinstance(conflict.local_change, AttachmentRestoration):
            self._delete_restored_attachment_marker(local_aid)

        if self._attachment_resolution_matches_remote(
            resolution.attachment_data,
            remote_state,
        ):
            self._delete_attachment_marker(local_aid)
            return

        self._upsert_attachment_marker(local_aid, remote_state)

    def _apply_local_feature_delete_resolution(
        self,
        resolution: ConflictResolution,
    ) -> None:
        conflict = resolution.conflict
        assert isinstance(conflict, LocalFeatureDeletionConflict)

        if any(
            isinstance(action, FeatureDeleteAction)
            for action in conflict.remote_actions
        ):
            self._remove_actions(conflict.remote_actions)
            self._cleanup_deleted_feature(conflict.local_change.fid)
            return

        if resolution.resolution_type == ResolutionType.Local:
            self._remove_actions(conflict.remote_actions)
            return

        if resolution.resolution_type == ResolutionType.Remote:
            self._restore_deleted_feature_from_backup(
                conflict.local_change.fid
            )
            return

        raise NotImplementedError

    def _apply_remote_feature_delete_resolution(
        self,
        resolution: ConflictResolution,
    ) -> None:
        conflict = resolution.conflict
        assert isinstance(conflict, RemoteFeatureDeletionConflict)

        if resolution.resolution_type == ResolutionType.Remote:
            self._clear_local_changes_for_remote_feature_delete(
                conflict.local_changes
            )
            return

        if resolution.resolution_type == ResolutionType.Local:
            local_fid = conflict.local_changes[0].fid
            self._set_feature_version(local_fid, conflict.remote_action.vid)
            self._remove_action(conflict.remote_action)
            self._delete_feature_update_markers(local_fid)
            self._add_restored_feature_marker(local_fid)
            return

        raise NotImplementedError

    def _apply_local_attachment_delete_resolution(
        self,
        resolution: ConflictResolution,
    ) -> None:
        conflict = resolution.conflict
        assert isinstance(conflict, LocalAttachmentDeletionConflict)

        if isinstance(conflict.remote_action, AttachmentDeleteAction):
            self._remove_action(conflict.remote_action)
            self._cleanup_deleted_attachment(conflict.local_change.aid)
            return

        if resolution.resolution_type == ResolutionType.Local:
            self._remove_action(conflict.remote_action)
            return

        if resolution.resolution_type == ResolutionType.Remote:
            self._delete_removed_attachment_marker(conflict.local_change.aid)
            return

        raise NotImplementedError

    def _apply_remote_attachment_delete_resolution(
        self,
        resolution: ConflictResolution,
    ) -> None:
        conflict = resolution.conflict
        assert isinstance(conflict, RemoteAttachmentDeletionConflict)

        if resolution.resolution_type == ResolutionType.Remote:
            self._delete_attachment_marker(conflict.local_change.aid)
            return

        if resolution.resolution_type == ResolutionType.Local:
            self._set_attachment_version(
                conflict.local_change.aid,
                conflict.remote_action.vid,
            )
            self._remove_action(conflict.remote_action)
            self._delete_attachment_marker(conflict.local_change.aid)
            self._add_restored_attachment_marker(conflict.local_change.aid)
            return

        raise NotImplementedError

    def _replace_action(
        self,
        old_action: VersioningAction,
        new_action: VersioningAction,
    ) -> None:
        for index, action in enumerate(self._remote_actions):
            if action != old_action:
                continue

            self._remote_actions[index] = new_action
            return

        raise KeyError

    def _remove_action(self, action: VersioningAction) -> None:
        self._remote_actions = [
            existing_action
            for existing_action in self._remote_actions
            if existing_action != action
        ]

    def _remove_actions(self, actions: Sequence[VersioningAction]) -> None:
        actions_to_remove = list(actions)
        self._remote_actions = [
            action
            for action in self._remote_actions
            if action not in actions_to_remove
        ]

    def _feature_layer(self) -> QgsVectorLayer:
        return QgsVectorLayer(
            detached_layer_uri(self._context),
            self._metadata.layer_name,
            "ogr",
        )

    def _feature_current_values(
        self,
        local_fid: FeatureId,
    ) -> Dict[FieldId, Any]:
        layer = self._feature_layer()
        feature = next(layer.getFeatures(QgsFeatureRequest([local_fid])), None)
        if feature is None:
            raise KeyError

        return {
            field.ngw_id: simplify_value(feature.attribute(field.attribute))
            for field in self._metadata.fields
        }

    def _feature_current_geometry(self, local_fid: FeatureId) -> QgsGeometry:
        layer = self._feature_layer()
        feature = next(layer.getFeatures(QgsFeatureRequest([local_fid])), None)
        if feature is None:
            raise KeyError

        return QgsGeometry(feature.geometry())

    def _feature_backups(
        self,
        local_fid: FeatureId,
    ) -> Tuple[Dict[FieldId, Any], Optional[QgsGeometry]]:
        field_backups: Dict[FieldId, Any] = {}
        geometry_backup: Optional[QgsGeometry] = None

        row = None
        with ContainerReadOnlySession(self._context) as cursor:
            for attribute, backup in cursor.execute(
                """
                SELECT attribute, backup
                FROM ngw_updated_attributes
                WHERE fid = ?
                """,
                (local_fid,),
            ):
                field = self._metadata.fields.get_with(attribute=attribute)
                field_backups[field.ngw_id] = deserialize_value(backup)

            row = cursor.execute(
                "SELECT backup FROM ngw_updated_geometries WHERE fid = ?",
                (local_fid,),
            ).fetchone()

        if row is not None:
            geometry_backup = deserialize_geometry(
                row[0],
                self._metadata.is_versioning_enabled,
            )

        return field_backups, geometry_backup

    def _remote_feature_state(
        self,
        conflict: FeatureDataConflict,
    ) -> Tuple[Dict[FieldId, Any], QgsGeometry]:
        current_values = self._feature_current_values(
            conflict.local_change.fid
        )
        field_backups, geometry_backup = self._feature_backups(
            conflict.local_change.fid
        )
        remote_values: Dict[FieldId, Any] = {}
        remote_changed_fields = conflict.remote_action.fields_dict

        for field in self._metadata.fields:
            after_sync_value = field_backups.get(
                field.ngw_id,
                current_values[field.ngw_id],
            )
            remote_values[field.ngw_id] = remote_changed_fields.get(
                field.ngw_id,
                after_sync_value,
            )

        current_geometry = self._feature_current_geometry(
            conflict.local_change.fid
        )
        after_sync_geometry = geometry_backup or current_geometry
        if isinstance(conflict.remote_action.geom, UnsetType):
            remote_geometry = after_sync_geometry
        else:
            remote_geometry = QgsGeometry(conflict.remote_action.geom)

        return remote_values, remote_geometry

    def _feature_resolution_fields(
        self,
        feature_data: FeatureResolutionData,
    ) -> Dict[FieldId, Any]:
        return {field_id: value for field_id, value in feature_data.fields}

    def _resolution_geometry(
        self,
        feature_data: FeatureResolutionData,
    ) -> QgsGeometry:
        return deserialize_geometry(
            feature_data.geom,
            self._metadata.is_versioning_enabled,
        )

    def _delete_feature_markers(
        self,
        local_fid: FeatureId,
        field_ids: Iterable[FieldId],
        delete_geometry: bool,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            for field_id in field_ids:
                attribute = self._metadata.fields.get_with(
                    ngw_id=field_id
                ).attribute
                cursor.execute(
                    """
                    DELETE FROM ngw_updated_attributes
                    WHERE fid = ? AND attribute = ?
                    """,
                    (local_fid, attribute),
                )

            if delete_geometry:
                cursor.execute(
                    "DELETE FROM ngw_updated_geometries WHERE fid = ?",
                    (local_fid,),
                )

    def _upsert_feature_field_markers(
        self,
        local_fid: FeatureId,
        values: Dict[FieldId, Any],
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            for field_id, value in values.items():
                attribute = self._metadata.fields.get_with(
                    ngw_id=field_id
                ).attribute
                cursor.execute(
                    """
                    INSERT INTO ngw_updated_attributes (fid, attribute, backup)
                    VALUES (?, ?, ?)
                    ON CONFLICT(fid, attribute) DO UPDATE SET
                        backup = excluded.backup
                    """,
                    (local_fid, attribute, serialize_value(value)),
                )

    def _upsert_feature_geometry_marker(
        self,
        local_fid: FeatureId,
        geometry: QgsGeometry,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                INSERT INTO ngw_updated_geometries (fid, backup)
                VALUES (?, ?)
                ON CONFLICT(fid) DO UPDATE SET
                    backup = excluded.backup
                """,
                (
                    local_fid,
                    serialize_geometry(
                        geometry,
                        self._metadata.is_versioning_enabled,
                    ),
                ),
            )

    def _geometries_equal(
        self,
        lhs: QgsGeometry,
        rhs: QgsGeometry,
    ) -> bool:
        if lhs.isEmpty():
            return rhs.isEmpty()

        if rhs.isEmpty():
            return False

        return lhs.equals(rhs)

    def _upsert_description_marker(
        self,
        local_fid: FeatureId,
        remote_value: Optional[str],
        remote_version: int,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                INSERT INTO ngw_updated_descriptions (fid, backup)
                VALUES (?, ?)
                ON CONFLICT(fid) DO UPDATE SET
                    backup = excluded.backup
                """,
                (
                    local_fid,
                    serialize_value(
                        {"value": remote_value, "version": remote_version}
                    ),
                ),
            )

    def _set_feature_version(
        self,
        local_fid: FeatureId,
        version: int,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                UPDATE ngw_features_metadata
                SET version = ?
                WHERE fid = ?
                """,
                (version, local_fid),
            )

    def _set_description_version(
        self,
        local_fid: FeatureId,
        version: int,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                UPDATE ngw_features_descriptions
                SET version = ?
                WHERE fid = ?
                """,
                (version, local_fid),
            )

    def _set_attachment_version(
        self,
        local_aid: AttachmentId,
        version: int,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                UPDATE ngw_features_attachments
                SET version = ?
                WHERE aid = ?
                """,
                (version, local_aid),
            )

    def _delete_description_marker(self, local_fid: FeatureId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_updated_descriptions WHERE fid = ?",
                (local_fid,),
            )

    def _attachment_action_without_conflicts(
        self,
        conflict: AttachmentDataConflict,
    ) -> Union[AttachmentUpdateAction, AttachmentRestoreAction]:
        remote_action = conflict.remote_action
        update_values: Dict[str, object] = {
            "keyname": remote_action.keyname,
            "name": remote_action.name,
            "description": remote_action.description,
            "mime_type": remote_action.mime_type,
            "fileobj": remote_action.fileobj,
        }

        for field_name in self._attachment_overlapping_fields(conflict):
            update_values[field_name] = Unset

        if self._is_attachment_file_conflict(conflict):
            update_values["fileobj"] = Unset
            update_values["mime_type"] = Unset

        return replace(remote_action, **update_values)

    def _attachment_overlapping_fields(
        self,
        conflict: AttachmentDataConflict,
    ) -> Set[str]:
        result = set()
        for field_name in ("keyname", "name", "description", "mime_type"):
            if isinstance(
                getattr(conflict.local_change, field_name), UnsetType
            ):
                continue
            if isinstance(
                getattr(conflict.remote_action, field_name), UnsetType
            ):
                continue
            result.add(field_name)
        return result

    def _is_attachment_file_conflict(
        self,
        conflict: AttachmentDataConflict,
    ) -> bool:
        return (
            conflict.local_change.is_file_new
            and conflict.remote_action.is_file_new
        )

    def _attachment_action_with_resolution(
        self,
        remote_action: Union[AttachmentUpdateAction, AttachmentRestoreAction],
        resolution_data: AttachmentResolutionData,
    ) -> Union[AttachmentUpdateAction, AttachmentRestoreAction]:
        return replace(
            remote_action,
            keyname=resolution_data.keyname or Unset,
            name=resolution_data.name,
            description=resolution_data.description,
            mime_type=resolution_data.mime_type or Unset,
            fileobj=resolution_data.fileobj
            if resolution_data.fileobj is not None
            else Unset,
        )

    def _current_attachment_state(
        self,
        local_aid: AttachmentId,
    ) -> Dict[str, Any]:
        row = None
        with ContainerReadOnlySession(self._context) as cursor:
            row = cursor.execute(
                """
                SELECT attachments.fid, metadata.ngw_fid, attachments.aid,
                       attachments.ngw_aid, attachments.version,
                       attachments.keyname, attachments.name,
                       attachments.description, attachments.fileobj,
                       attachments.mime_type
                FROM ngw_features_attachments AS attachments
                LEFT JOIN ngw_features_metadata AS metadata
                    ON metadata.fid = attachments.fid
                WHERE attachments.aid = ?
                """,
                (local_aid,),
            ).fetchone()

        if row is None:
            raise KeyError

        return {
            "fid": row[0],
            "ngw_fid": row[1],
            "aid": row[2],
            "ngw_aid": row[3],
            "version": row[4],
            "keyname": row[5],
            "name": row[6],
            "description": row[7],
            "fileobj": row[8],
            "mime_type": row[9],
        }

    def _attachment_backup_state(
        self,
        local_aid: AttachmentId,
    ) -> Dict[str, Any]:
        current_state = self._current_attachment_state(local_aid)
        row = None
        with ContainerReadOnlySession(self._context) as cursor:
            row = cursor.execute(
                "SELECT backup FROM ngw_updated_attachments WHERE aid = ?",
                (local_aid,),
            ).fetchone()

        if row is None or row[0] is None:
            return current_state

        backup = json.loads(row[0])
        return {
            "fid": backup["fid"],
            "ngw_fid": backup["ngw_fid"],
            "aid": backup["aid"],
            "ngw_aid": backup["ngw_aid"],
            "version": deserialize_value(backup["version"]),
            "keyname": backup["keyname"],
            "name": backup["name"],
            "description": backup["description"],
            "fileobj": deserialize_value(backup["fileobj"]),
            "mime_type": backup["mime_type"],
        }

    def _remote_attachment_state(
        self,
        conflict: AttachmentDataConflict,
    ) -> Dict[str, Any]:
        state = dict(self._attachment_backup_state(conflict.local_change.aid))
        state["version"] = conflict.remote_action.vid

        for field_name in ("keyname", "name", "description", "mime_type"):
            value = getattr(conflict.remote_action, field_name)
            if isinstance(value, UnsetType):
                continue
            state[field_name] = value

        if not isinstance(conflict.remote_action.fileobj, UnsetType):
            state["fileobj"] = conflict.remote_action.fileobj

        return state

    def _attachment_backup_payload(self, state: Dict[str, Any]) -> str:
        return json.dumps(
            {
                "fid": state["fid"],
                "ngw_fid": state["ngw_fid"],
                "aid": state["aid"],
                "ngw_aid": state["ngw_aid"],
                "version": serialize_value(state["version"]),
                "keyname": state["keyname"],
                "name": state["name"],
                "description": state["description"],
                "fileobj": serialize_value(state["fileobj"]),
                "mime_type": state["mime_type"],
            }
        )

    def _upsert_attachment_marker(
        self,
        local_aid: AttachmentId,
        remote_state: Dict[str, Any],
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                INSERT INTO ngw_updated_attachments (aid, backup)
                VALUES (?, ?)
                ON CONFLICT(aid) DO UPDATE SET
                    backup = excluded.backup
                """,
                (local_aid, self._attachment_backup_payload(remote_state)),
            )

    def _delete_attachment_marker(self, local_aid: AttachmentId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_updated_attachments WHERE aid = ?",
                (local_aid,),
            )

    def _delete_restored_feature_marker(self, local_fid: FeatureId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_restored_features WHERE fid = ?",
                (local_fid,),
            )

    def _delete_restored_attachment_marker(
        self,
        local_aid: AttachmentId,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_restored_attachments WHERE aid = ?",
                (local_aid,),
            )

    def _delete_removed_attachment_marker(
        self,
        local_aid: AttachmentId,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_removed_attachments WHERE aid = ?",
                (local_aid,),
            )

    def _has_attachment_local_changes_after_remote(
        self,
        conflict: AttachmentDataConflict,
    ) -> bool:
        local_fields = {
            field_name
            for field_name in ("keyname", "name", "description", "mime_type")
            if not isinstance(
                getattr(conflict.local_change, field_name), UnsetType
            )
        }
        remote_fields = {
            field_name
            for field_name in ("keyname", "name", "description", "mime_type")
            if not isinstance(
                getattr(conflict.remote_action, field_name), UnsetType
            )
        }

        if local_fields - remote_fields:
            return True

        return (
            conflict.local_change.is_file_new
            and not conflict.remote_action.is_file_new
        )

    def _attachment_resolution_matches_remote(
        self,
        resolution_data: AttachmentResolutionData,
        remote_state: Dict[str, Any],
    ) -> bool:
        if resolution_data.keyname != remote_state["keyname"]:
            return False
        if resolution_data.name != remote_state["name"]:
            return False
        if resolution_data.description != remote_state["description"]:
            return False
        if resolution_data.mime_type != remote_state["mime_type"]:
            return False

        remote_file_object = remote_state["fileobj"]
        if isinstance(remote_file_object, UnsetType):
            remote_file_object = None

        return resolution_data.fileobj == remote_file_object

    def _cleanup_deleted_feature(self, local_fid: FeatureId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.executescript(
                f"""
                DELETE FROM ngw_removed_features WHERE fid = {local_fid};
                DELETE FROM ngw_features_metadata WHERE fid = {local_fid};
                """
            )

    def _cleanup_deleted_attachment(self, local_aid: AttachmentId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.executescript(
                f"""
                DELETE FROM ngw_removed_attachments WHERE aid = {local_aid};
                DELETE FROM ngw_features_attachments WHERE aid = {local_aid};
                """
            )

    def _restore_deleted_feature_from_backup(
        self, local_fid: FeatureId
    ) -> None:
        row = None
        with ContainerReadOnlySession(self._context) as cursor:
            row = cursor.execute(
                "SELECT backup FROM ngw_removed_features WHERE fid = ?",
                (local_fid,),
            ).fetchone()

        if row is None:
            raise KeyError

        backup = json.loads(row[0])
        after_sync = backup["after_sync"]

        layer = self._feature_layer()
        feature = QgsFeature(layer.fields(), local_fid)
        feature.setAttribute(self._metadata.fid_field, local_fid)

        for field_ngw_id, value in after_sync["fields"]:
            attribute = self._metadata.fields.get_with(
                ngw_id=field_ngw_id
            ).attribute
            feature.setAttribute(attribute, value)

        feature.setGeometry(
            deserialize_geometry(
                after_sync["geom"],
                self._metadata.is_versioning_enabled,
            )
        )

        layer.startEditing()
        is_success = layer.addFeature(feature)
        if not is_success:
            layer.rollBack()
            raise DetachedEditingError
        layer.commitChanges()

        description_data = after_sync["description"]
        attachments_data = after_sync["attachments"]

        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                "DELETE FROM ngw_removed_features WHERE fid = ?",
                (local_fid,),
            )
            cursor.execute(
                "DELETE FROM ngw_features_descriptions WHERE fid = ?",
                (local_fid,),
            )
            cursor.execute(
                "DELETE FROM ngw_features_attachments WHERE fid = ?",
                (local_fid,),
            )

            if description_data:
                cursor.execute(
                    """
                    INSERT INTO ngw_features_descriptions (fid, version, description)
                    VALUES (?, ?, ?)
                    """,
                    (
                        local_fid,
                        deserialize_value(description_data["version"]),
                        description_data["value"],
                    ),
                )

            for attachment_data in attachments_data:
                cursor.execute(
                    """
                    INSERT INTO ngw_features_attachments (
                        fid, aid, ngw_aid, version, keyname, name,
                        description, fileobj, mime_type
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        attachment_data["fid"],
                        attachment_data["aid"],
                        attachment_data["ngw_aid"],
                        deserialize_value(attachment_data["version"]),
                        attachment_data["keyname"],
                        attachment_data["name"],
                        attachment_data["description"],
                        deserialize_value(attachment_data["fileobj"]),
                        attachment_data["mime_type"],
                    ),
                )

    def _clear_local_changes_for_remote_feature_delete(
        self,
        local_changes: Sequence[object],
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            for change in local_changes:
                if isinstance(change, FeatureUpdate):
                    for field_id in change.fields_dict.keys():
                        attribute = self._metadata.fields.get_with(
                            ngw_id=field_id
                        ).attribute
                        cursor.execute(
                            """
                            DELETE FROM ngw_updated_attributes
                            WHERE fid = ? AND attribute = ?
                            """,
                            (change.fid, attribute),
                        )

                    if not isinstance(change.geometry, UnsetType):
                        cursor.execute(
                            "DELETE FROM ngw_updated_geometries WHERE fid = ?",
                            (change.fid,),
                        )

                elif isinstance(change, DescriptionPut):
                    cursor.execute(
                        "DELETE FROM ngw_updated_descriptions WHERE fid = ?",
                        (change.fid,),
                    )

                elif isinstance(change, AttachmentUpdate):
                    cursor.execute(
                        "DELETE FROM ngw_updated_attachments WHERE aid = ?",
                        (change.aid,),
                    )

                elif isinstance(change, AttachmentDeletion):
                    cursor.execute(
                        "DELETE FROM ngw_removed_attachments WHERE aid = ?",
                        (change.aid,),
                    )

                elif isinstance(change, AttachmentCreation):
                    cursor.execute(
                        "DELETE FROM ngw_added_attachments WHERE aid = ?",
                        (change.aid,),
                    )

    def _delete_feature_update_markers(self, local_fid: FeatureId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.executescript(
                f"""
                DELETE FROM ngw_updated_attributes WHERE fid = {local_fid};
                DELETE FROM ngw_updated_geometries WHERE fid = {local_fid};
                """
            )

    def _add_restored_feature_marker(self, local_fid: FeatureId) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                INSERT INTO ngw_restored_features (fid)
                VALUES (?)
                ON CONFLICT(fid) DO NOTHING
                """,
                (local_fid,),
            )

    def _add_restored_attachment_marker(
        self,
        local_aid: AttachmentId,
    ) -> None:
        with ContainerReadWriteSession(self._context) as cursor:
            cursor.execute(
                """
                INSERT INTO ngw_restored_attachments (aid)
                VALUES (?)
                ON CONFLICT(aid) DO NOTHING
                """,
                (local_aid,),
            )
