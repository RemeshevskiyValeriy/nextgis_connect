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

import uuid
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Union

from qgis.core import QgsApplication, QgsFeedback, QgsTask
from qgis.PyQt.QtCore import pyqtSignal

from nextgis_connect.legacy.detached_editing.storage_service_factory import (
    DetachedStorageServiceFactory,
)
from nextgis_connect.legacy.detached_editing.utils import AttachmentMetadata
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.tasks import NgConnectTask
from nextgis_connect.shared.types import AttachmentId


@dataclass(frozen=True)
class AttachmentDownloadContext:
    connection_id: str
    connection_url: str
    connection_domain_uuid: str
    resource_id: int
    feature_ngw_fid: Union[str, int]
    attachment: AttachmentMetadata
    attachment_path: Path


class AttachmentDownloadTask(NgConnectTask):
    def __init__(self, context: AttachmentDownloadContext) -> None:
        super().__init__(flags=QgsTask.Flags())
        self.setDescription(
            QgsApplication.translate(
                "AttachmentsTab", "Downloading attachment"
            )
        )
        self.context = context
        self._feedback: Optional[QgsFeedback] = None

    @property
    def attachment_id(self) -> AttachmentId:
        return self.context.attachment.aid

    def run(self) -> bool:
        if not super().run():
            return False

        feedback = QgsFeedback()
        feedback.progressChanged.connect(self.setProgress)
        self._feedback = feedback

        try:
            self.download(self.context, feedback=feedback)
        except Exception as error:
            logger.exception("Failed to download attachment")
            self._error = error
            return False
        finally:
            self._feedback = None

        return True

    def cancel(self) -> None:
        feedback = self._feedback
        if feedback is not None:
            feedback.cancel()
        super().cancel()

    @staticmethod
    def download(
        context: AttachmentDownloadContext,
        *,
        feedback: Optional[QgsFeedback] = None,
    ) -> None:
        attachment = context.attachment
        assert attachment.ngw_aid is not None
        url = (
            context.connection_url + f"/api/resource/{context.resource_id}"
            f"/feature/{context.feature_ngw_fid}"
            f"/attachment/{attachment.ngw_aid}/download"
        )

        context.attachment_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = context.attachment_path.with_name(
            f"{context.attachment_path.name}.{uuid.uuid4().hex}.download"
        )

        try:
            ngw_connection = QgsNgwConnection(context.connection_id)
            ngw_connection.download(
                url,
                str(temporary_path),
                feedback=feedback,
            )
            temporary_path.replace(context.attachment_path)
        finally:
            with suppress(FileNotFoundError):
                temporary_path.unlink()

        DetachedStorageServiceFactory.create().register_attachment_file(
            context.connection_domain_uuid,
            context.resource_id,
            attachment.aid,
            file_name=attachment.name,
            mime_type=attachment.mime_type,
            fileobj=attachment.fileobj,
            feature_local_id=int(attachment.fid),
            feature_ngw_fid=attachment.ngw_fid,
            ngw_aid=attachment.ngw_aid,
        )


class AttachmentBatchDownloadTask(NgConnectTask):
    attachment_progress_changed = pyqtSignal(int, float)
    attachment_finished = pyqtSignal(int)

    def __init__(self, contexts: List[AttachmentDownloadContext]) -> None:
        super().__init__(flags=QgsTask.Flags())
        self.setDescription(
            QgsApplication.translate(
                "AttachmentsTab", "Downloading attachments"
            )
        )
        self.contexts = list(contexts)
        self._feedback: Optional[QgsFeedback] = None
        self._failed_attachment_ids: List[AttachmentId] = []

    @property
    def attachment_ids(self) -> List[AttachmentId]:
        return [context.attachment.aid for context in self.contexts]

    @property
    def failed_attachment_ids(self) -> List[AttachmentId]:
        return self._failed_attachment_ids

    def run(self) -> bool:
        if not super().run():
            return False

        total = len(self.contexts)
        for index, context in enumerate(self.contexts, start=1):
            if self.isCanceled():
                return False

            self._download_context(context)
            if total:
                self.setProgress(index / total * 100)

        return True

    def cancel(self) -> None:
        feedback = self._feedback
        if feedback is not None:
            feedback.cancel()
        super().cancel()

    def _download_context(self, context: AttachmentDownloadContext) -> None:
        attachment_id = context.attachment.aid
        feedback = QgsFeedback()
        feedback.progressChanged.connect(
            lambda progress, aid=attachment_id: (
                self.attachment_progress_changed.emit(aid, progress)
            )
        )
        self._feedback = feedback
        self.attachment_progress_changed.emit(attachment_id, 0.0)
        try:
            AttachmentDownloadTask.download(context, feedback=feedback)
            self.attachment_progress_changed.emit(attachment_id, 100.0)
        except Exception:
            self._failed_attachment_ids.append(attachment_id)
            logger.warning(
                "Failed to download attachment: %s",
                context.attachment,
                exc_info=True,
            )
        finally:
            self._feedback = None
            self.attachment_finished.emit(attachment_id)
