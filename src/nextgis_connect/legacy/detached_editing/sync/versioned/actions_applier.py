import sqlite3
from contextlib import closing
from copy import deepcopy
from pathlib import Path
from typing import List, Optional, Sequence, Set, Tuple, Union

from qgis.core import (
    QgsEditError,
    QgsFeature,
    QgsVectorLayer,
    edit,
)
from qgis.PyQt.QtCore import QObject, pyqtSlot

from nextgis_connect.detached_editing.sync.versioned.actions import (
    ActionType,
    AttachmentCreateAction,
    AttachmentDeleteAction,
    AttachmentRestoreAction,
    AttachmentUpdateAction,
    ContinueAction,
    DescriptionPutAction,
    FeatureAction,
    FeatureCreateAction,
    FeatureDeleteAction,
    FeatureUpdateAction,
)
from nextgis_connect.detached_editing.utils import (
    DetachedContainerMetaData,
    FeatureMetadata,
    detached_layer_uri,
    make_connection,
)
from nextgis_connect.platform.qgis.errors import (
    ContainerError,
    LayerEditError,
    NgConnectError,
    SynchronizationError,
)
from nextgis_connect.shared.types import AttachmentId, FeatureId, UnsetType


class ActionApplier(QObject):
    _container_path: Path
    _layer: QgsVectorLayer
    _metadata: DetachedContainerMetaData

    _additional_changes: List[Tuple[str, Tuple]]
    _create_command_ids: List

    def __init__(
        self, container_path: Path, metadata: DetachedContainerMetaData
    ) -> None:
        super().__init__()

        self._container_path = container_path
        self._metadata = metadata
        self._layer = QgsVectorLayer(
            detached_layer_uri(container_path, metadata)
        )

        self._additional_changes = []
        self._create_command_ids = []

    def apply(self, actions: Sequence[FeatureAction]) -> None:
        if len(actions) == 0:
            return

        self._additional_changes = []
        self._create_command_ids = []

        try:
            self._layer.committedFeaturesAdded.connect(
                self._update_create_commands
            )
            self._apply_actions(actions)

        except NgConnectError:
            raise

        except sqlite3.Error as error:
            raise ContainerError from error

        except QgsEditError as error:
            raise SynchronizationError from LayerEditError.from_qgis_error(
                deepcopy(error)
            )

        except Exception as error:
            raise SynchronizationError from error

        finally:
            self._layer.committedFeaturesAdded.disconnect(
                self._update_create_commands
            )

    def _apply_actions(self, actions: Sequence[FeatureAction]) -> None:
        APPLIER_FOR_ACTION = {
            ActionType.FEATURE_CREATE: self._create_feature,
            ActionType.FEATURE_UPDATE: self._update_feature,
            ActionType.FEATURE_DELETE: self._delete_feature,
            ActionType.DESCRIPTION_PUT: self._put_description,
            ActionType.ATTACHMENT_CREATE: self._create_attachment,
            ActionType.ATTACHMENT_UPDATE: self._update_attachment,
            ActionType.ATTACHMENT_DELETE: self._delete_attachment,
            ActionType.CONTINUE: self._continue,
        }

        # Filter objects added and deleted by this client in the previous step
        # (UploadChangesTask) to avoid reapplying changes and only update
        # their version.
        previously_added, previously_deleted = (
            self._extract_previously_uploaded(actions)
        )

        with edit(self._layer):
            for action in actions:
                action_type = action.TYPE
                params = (action,)

                if action_type == ActionType.FEATURE_RESTORE:
                    action_type = (
                        ActionType.FEATURE_UPDATE
                        if self._get_feature_metadata(ngw_fid=action.fid)
                        is not None
                        else ActionType.FEATURE_CREATE
                    )

                if action_type == ActionType.ATTACHMENT_RESTORE:
                    assert isinstance(action, AttachmentRestoreAction)
                    action_type = (
                        ActionType.ATTACHMENT_UPDATE
                        if self._get_attachment_id(
                            ngw_fid=action.fid,
                            ngw_aid=action.aid,
                        )
                        is not None
                        else ActionType.ATTACHMENT_CREATE
                    )

                if action_type == ActionType.FEATURE_CREATE:
                    params = (action, previously_added)
                elif action_type == ActionType.FEATURE_DELETE:
                    params = (action, previously_deleted)

                APPLIER_FOR_ACTION[action_type](*params)

        # Apply metadata and extension changes (descriptions, attachments)
        with closing(
            make_connection(self._container_path)
        ) as connection, closing(connection.cursor()) as cursor:
            for command in self._additional_changes:
                cursor.execute(*command)

            connection.commit()

    def _extract_previously_uploaded(
        self, actions: Sequence[FeatureAction]
    ) -> Tuple[Set[FeatureId], Set[FeatureId]]:
        if not self._metadata.is_versioning_enabled:
            return (set(), set())

        added_ngw_fids = set()
        deleted_ngw_fids = set()

        for action in actions:
            if isinstance(action, FeatureCreateAction):
                added_ngw_fids.add(action.fid)
            if isinstance(action, FeatureDeleteAction):
                deleted_ngw_fids.add(action.fid)

        if len(added_ngw_fids) == 0 and len(deleted_ngw_fids) == 0:
            return (set(), set())

        already_added = set()
        already_deleted = set()

        with closing(
            make_connection(self._container_path)
        ) as connection, closing(connection.cursor()) as cursor:
            if len(added_ngw_fids) > 0:
                added_fids = ",".join(str(fid) for fid in added_ngw_fids)
                already_added = set(
                    row[0]
                    for row in cursor.execute(
                        f"""
                        SELECT ngw_fid FROM ngw_features_metadata
                            WHERE ngw_fid IN ({added_fids})
                        """
                    )
                )

            if len(deleted_ngw_fids) > 0:
                deleted_fids = ",".join(str(fid) for fid in deleted_ngw_fids)
                still_existed = set(
                    row[0]
                    for row in cursor.execute(
                        f"""
                        SELECT ngw_fid FROM ngw_features_metadata
                            WHERE ngw_fid IN ({deleted_fids})
                        """
                    )
                )
                already_deleted = deleted_ngw_fids - still_existed

        return (already_added, already_deleted)

    def _create_feature(
        self,
        action: FeatureCreateAction,
        previously_added: Set[FeatureId],
    ) -> None:
        # Update version if feature were added in previous sync
        if action.fid in previously_added:
            self._additional_changes.append(
                (
                    "UPDATE ngw_features_metadata SET version=? WHERE ngw_fid=?",
                    (action.vid, action.fid),
                )
            )
            return

        fields = self._metadata.fields

        # Create new feature
        new_feature = QgsFeature(self._layer.fields())
        if not isinstance(action.fields, UnsetType):
            for field_ngw_id, value in action.fields:
                attribute = fields.get_with(ngw_id=field_ngw_id).attribute
                new_feature.setAttribute(attribute, value)
        if not isinstance(action.geom, UnsetType):
            new_feature.setGeometry(action.geom)

        is_success = self._layer.addFeature(new_feature)
        if not is_success:
            raise SynchronizationError("Can't add feature")

        # Create metadata for feature
        self._create_command_ids.append(len(self._additional_changes))
        self._additional_changes.append(
            (
                "INSERT INTO ngw_features_metadata (fid, ngw_fid, version) VALUES (?, ?, ?)",
                # fid will be set in _update_create_commands
                (action.fid, action.vid),
            )
        )

    def _update_feature(self, action: FeatureUpdateAction) -> None:
        feature_metadata = self._get_feature_metadata(ngw_fid=action.fid)
        if feature_metadata is None:
            message = f"Feature with fid={action.fid} is not exist"
            raise SynchronizationError(message)

        assert feature_metadata.fid is not None

        fields = self._metadata.fields

        # Update fields
        action_fields = (
            action.fields if not isinstance(action.fields, UnsetType) else []
        )
        fields_values = {
            fields.get_with(ngw_id=ngw_field_id).attribute: value
            for ngw_field_id, value in action_fields
        }
        if len(fields_values) > 0:
            is_success = self._layer.changeAttributeValues(
                feature_metadata.fid, fields_values
            )
            if not is_success:
                raise SynchronizationError("Can't update fields")

        # Update geometry
        if not isinstance(action.geom, UnsetType):
            geom = action.geom
            is_success = self._layer.changeGeometry(feature_metadata.fid, geom)
            if not is_success:
                raise SynchronizationError("Can't update geometry")

        # Update feature metadata
        self._additional_changes.append(
            (
                "UPDATE ngw_features_metadata SET version=? WHERE ngw_fid=?",
                (action.vid, feature_metadata.ngw_fid),
            )
        )

    def _delete_feature(
        self, action: FeatureDeleteAction, previously_deleted: Set[FeatureId]
    ) -> None:
        if action.fid in previously_deleted:
            return

        feature_metadata = self._get_feature_metadata(ngw_fid=action.fid)
        if feature_metadata is None:
            message = f"Feature with fid={action.fid} is not exist"
            raise SynchronizationError(message)

        assert feature_metadata.fid is not None

        # Delete feature
        is_success = self._layer.deleteFeature(feature_metadata.fid)
        if not is_success:
            raise SynchronizationError(
                f"Can't delete feature with fid={feature_metadata.fid}"
            )

        # Delete feature metadata
        self._additional_changes.append(
            (
                "DELETE FROM ngw_features_metadata WHERE fid=?",
                (feature_metadata.fid,),
            )
        )

    def _put_description(self, action: DescriptionPutAction) -> None:
        self._additional_changes.append(
            (
                """
                INSERT INTO ngw_features_descriptions (fid, version, description)
                SELECT fid, ?, ?
                FROM ngw_features_metadata WHERE ngw_fid=?
                ON CONFLICT(fid) DO UPDATE SET
                    version = ?,
                    description = ?
                """,
                (
                    action.vid,
                    action.value,
                    action.fid,
                    action.vid,
                    action.value,
                ),
            )
        )

    def _create_attachment(
        self,
        action: Union[AttachmentCreateAction, AttachmentRestoreAction],
    ) -> None:
        self._additional_changes.append(
            (
                """
                INSERT INTO ngw_features_attachments (
                    fid, ngw_aid, version, keyname, name, description, fileobj, mime_type
                )
                SELECT fid, ?, ?, ?, ?, ?, ?, ?
                FROM ngw_features_metadata WHERE ngw_fid=?
                ON CONFLICT(ngw_aid) DO UPDATE SET
                    version = ?,
                    keyname = ?,
                    name = ?,
                    description = ?,
                    fileobj = ?,
                    mime_type = ?
                """,
                (
                    action.aid,
                    action.vid,
                    action.keyname or None,
                    action.name or None,
                    action.description or None,
                    action.fileobj or None,
                    action.mime_type or None,
                    # ngw_fid
                    action.fid,
                    action.vid,
                    action.keyname or None,
                    action.name or None,
                    action.description or None,
                    action.fileobj or None,
                    action.mime_type or None,
                ),
            )
        )

    def _update_attachment(
        self,
        action: Union[AttachmentUpdateAction, AttachmentRestoreAction],
    ) -> None:
        sets = ["version=?"]
        params: List = [action.vid]

        if action.keyname:
            sets.append("keyname=?")
            params.append(action.keyname)

        if action.name:
            sets.append("name=?")
            params.append(action.name)

        if action.description:
            sets.append("description=?")
            params.append(action.description)

        if bool(action.fileobj) and action.fileobj != -1:
            sets.append("fileobj=?")
            params.append(action.fileobj)

        if action.mime_type:
            sets.append("mime_type=?")
            params.append(action.mime_type)

        sql = f"""
               UPDATE ngw_features_attachments
               SET {", ".join(sets)}
               WHERE ngw_aid=? AND fid=(
                   SELECT fid FROM ngw_features_metadata WHERE ngw_fid=?
               )
        """

        # Add WHERE parameters: ngw_aid and ngw_fid
        params.append(action.aid)
        params.append(action.fid)

        self._additional_changes.append((sql, tuple(params)))

    def _delete_attachment(self, action: AttachmentDeleteAction) -> None:
        self._additional_changes.append(
            (
                """
                DELETE FROM ngw_features_attachments WHERE ngw_aid=? AND fid=(
                    SELECT fid FROM ngw_features_metadata WHERE ngw_fid=?
                )
                """,
                (action.aid, action.fid),
            )
        )

    def _continue(self, action: ContinueAction) -> None:
        pass

    def _get_feature_metadata(
        self, *, ngw_fid: FeatureId
    ) -> Optional[FeatureMetadata]:
        query = f"SELECT * FROM ngw_features_metadata WHERE ngw_fid={ngw_fid}"
        try:
            with closing(
                make_connection(self._container_path)
            ) as connection, closing(connection.cursor()) as cursor:
                result = [
                    FeatureMetadata(*row) for row in cursor.execute(query)
                ]

        except Exception as error:
            raise ContainerError from error

        assert len(result) <= 1, "More than one feature with one ngw_fid"

        return result[0] if len(result) == 1 else None

    def _get_attachment_id(
        self,
        *,
        ngw_fid: FeatureId,
        ngw_aid: AttachmentId,
    ) -> Optional[AttachmentId]:
        query = """
            SELECT attachments.aid
            FROM ngw_features_attachments AS attachments
            JOIN ngw_features_metadata AS metadata
                ON metadata.fid = attachments.fid
            WHERE metadata.ngw_fid = ? AND attachments.ngw_aid = ?
        """
        try:
            with closing(
                make_connection(self._container_path)
            ) as connection, closing(connection.cursor()) as cursor:
                result = [
                    row[0] for row in cursor.execute(query, (ngw_fid, ngw_aid))
                ]

        except Exception as error:
            raise ContainerError from error

        assert len(result) <= 1, "More than one attachment with one ngw_aid"

        return result[0] if len(result) == 1 else None

    @pyqtSlot(str, "QgsFeatureList")
    def _update_create_commands(
        self, _: str, features: List[QgsFeature]
    ) -> None:
        for command_id, feature in zip(self._create_command_ids, features):
            command = self._additional_changes[command_id]
            self._additional_changes[command_id] = (
                command[0],
                (feature.id(), *command[1]),
            )
