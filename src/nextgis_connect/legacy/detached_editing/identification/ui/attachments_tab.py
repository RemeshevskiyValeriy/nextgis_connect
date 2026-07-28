import shutil
from contextlib import closing, contextmanager, suppress
from pathlib import Path
from typing import Any, Iterator, List, Optional, Set, Tuple, Union, cast
from zipfile import ZIP_DEFLATED, ZipFile

from qgis.core import (
    QgsApplication,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsTask,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import (
    QByteArray,
    QMimeDatabase,
    QModelIndex,
    Qt,
    QUrl,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QDesktopServices, QImageReader
from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QListView,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nextgis_connect.bootstrap.plugin_interface import NgConnectInterface
from nextgis_connect.legacy.detached_editing.detached_layer import (
    DetachedLayer,
)
from nextgis_connect.legacy.detached_editing.identification.attachments_model import (
    AttachmentsModel,
)
from nextgis_connect.legacy.detached_editing.identification.attachments_sort_proxy_model import (
    AttachmentsSortMode,
    AttachmentsSortProxyModel,
)
from nextgis_connect.legacy.detached_editing.identification.settings import (
    IdentificationSettings,
)
from nextgis_connect.legacy.detached_editing.identification.ui.attachments_view_wrapper import (
    AttachmentsViewWrapper,
)
from nextgis_connect.legacy.detached_editing.utils import (
    AttachmentMetadata,
    make_connection,
)
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.legacy.ngw_connection import (
    NgwConnection,
    NgwConnectionsManager,
)
from nextgis_connect.platform.filesystem import reveal_in_file_manager
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.compat import QgsFeatureId
from nextgis_connect.platform.tasks.ng_connect_task import NgConnectTask
from nextgis_connect.shared.types import AttachmentId
from nextgis_connect.ui_kit.icons.icon import material_icon, qgis_icon

AttachmentThumbnailKey = Tuple[
    str,
    int,
    Union[str, int],
    Union[str, int],
    Optional[Union[str, int]],
    Optional[str],
]


def _is_image_attachment(attachment: AttachmentMetadata) -> bool:
    mime_type = attachment.mime_type or ""
    settings = IdentificationSettings()
    return (
        mime_type in settings.attachment_thumbnail_mime_types
        or mime_type.startswith("image/")
    )


def _needs_attachment_thumbnail_download(
    attachment: AttachmentMetadata,
) -> bool:
    return (
        _is_image_attachment(attachment)
        and attachment.thumbnail_path is not None
        and not attachment.thumbnail_path.exists()
        and attachment.ngw_fid is not None
        and attachment.ngw_aid is not None
    )


def _download_attachment_thumbnail(
    connection_id: str,
    resource_id: int,
    feature_ngw_fid: Union[str, int],
    ngw_aid: Union[str, int],
    thumbnail_path: Path,
) -> None:
    url = (
        f"/api/resource/{resource_id}"
        f"/feature/{feature_ngw_fid}"
        f"/attachment/{ngw_aid}"
        "/image?size=64x64&crop=true"
    )

    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    data = QgsNgwConnection(connection_id).get(url)
    if isinstance(data, QByteArray):
        thumbnail_path.write_bytes(bytes(data))
    elif isinstance(data, (bytes, bytearray)):
        thumbnail_path.write_bytes(bytes(data))
    else:
        message = "Unexpected attachment thumbnail response"
        raise RuntimeError(message)

    image_reader = QImageReader(str(thumbnail_path))
    if image_reader.canRead():
        return

    error = image_reader.errorString()
    if thumbnail_path.exists():
        thumbnail_path.unlink()

    message = f"Attachment thumbnail response is not an image: {error}"
    raise RuntimeError(message)


def _attachment_thumbnail_key(
    connection_id: str,
    resource_id: int,
    attachment: AttachmentMetadata,
) -> AttachmentThumbnailKey:
    assert attachment.ngw_fid is not None
    assert attachment.ngw_aid is not None
    return (
        connection_id,
        resource_id,
        attachment.ngw_fid,
        attachment.ngw_aid,
        attachment.fileobj,
        attachment.sha256,
    )


class IdentificationAttachmentsTask(NgConnectTask):
    def __init__(
        self,
        detached_layer: DetachedLayer,
        feature_id: QgsFeatureId,
        generation: int,
        keep_existing: bool = False,
    ) -> None:
        super().__init__(flags=QgsTask.Flags())
        self.setDescription(
            QgsApplication.translate(
                "AttachmentsTab", "Loading feature attachments"
            )
        )
        self.detached_layer = detached_layer
        self.feature_id = feature_id
        self.generation = generation
        self.keep_existing = keep_existing
        self._attachments: List[AttachmentMetadata] = []

    @property
    def attachments(self) -> List[AttachmentMetadata]:
        return self._attachments

    def run(self) -> bool:
        if not super().run():
            return False

        try:
            self._attachments = (
                self.detached_layer.feature_attachments_for_identification(
                    self.feature_id
                )
            )
        except Exception as error:
            logger.exception("Failed to load feature attachments")
            self._error = error
            return False

        return True


class AttachmentThumbnailsTask(NgConnectTask):
    def __init__(
        self,
        attachments: List[AttachmentMetadata],
        connection_id: str,
        resource_id: int,
        generation: int,
    ) -> None:
        super().__init__(flags=QgsTask.Flags())
        self.setDescription(
            QgsApplication.translate(
                "AttachmentsTab", "Loading attachment previews"
            )
        )
        self.attachments = list(attachments)
        self.connection_id = connection_id
        self.resource_id = resource_id
        self.generation = generation
        self._changed_attachment_ids: List[AttachmentId] = []
        self._failed_thumbnail_keys: Set[AttachmentThumbnailKey] = set()

    @property
    def changed_attachment_ids(self) -> List[AttachmentId]:
        return self._changed_attachment_ids

    @property
    def failed_thumbnail_keys(self) -> Set[AttachmentThumbnailKey]:
        return self._failed_thumbnail_keys

    def run(self) -> bool:
        if not super().run():
            return False

        total = len(self.attachments)
        for index, attachment in enumerate(self.attachments, start=1):
            if self.isCanceled():
                return False

            self._download_thumbnail(attachment)
            if total:
                self.setProgress(index / total * 100)

        return True

    def _download_thumbnail(self, attachment: AttachmentMetadata) -> None:
        if not self._needs_thumbnail_download(attachment):
            return

        assert attachment.thumbnail_path is not None
        assert attachment.ngw_fid is not None
        assert attachment.ngw_aid is not None

        try:
            _download_attachment_thumbnail(
                self.connection_id,
                self.resource_id,
                attachment.ngw_fid,
                attachment.ngw_aid,
                attachment.thumbnail_path,
            )
        except Exception:
            if attachment.thumbnail_path.exists():
                attachment.thumbnail_path.unlink()
            self._failed_thumbnail_keys.add(
                _attachment_thumbnail_key(
                    self.connection_id,
                    self.resource_id,
                    attachment,
                )
            )
            logger.warning(
                "Failed to download attachment thumbnail: %s",
                attachment,
                exc_info=True,
            )
            return

        self._changed_attachment_ids.append(attachment.aid)

    def _needs_thumbnail_download(
        self, attachment: AttachmentMetadata
    ) -> bool:
        return _needs_attachment_thumbnail_download(attachment)


class AttachmentsTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._detached_layer: Optional[DetachedLayer] = None
        self._feature_id: Optional[QgsFeatureId] = None
        self._loading_generation = 0
        self._attachments_task: Optional[IdentificationAttachmentsTask] = None
        self._thumbnails_task: Optional[AttachmentThumbnailsTask] = None
        self._failed_thumbnail_keys: Set[AttachmentThumbnailKey] = set()
        self._is_read_only = True

        self._attachment_added_connection: Optional[Any] = None
        self._attachment_updated_connection: Optional[Any] = None
        self._attachment_removed_connection: Optional[Any] = None

        self._load_ui()

    @property
    def view(self) -> QListView:
        return self._view_wrapper.view

    def set_feature(
        self, layer: QgsVectorLayer, feature_id: QgsFeatureId
    ) -> None:
        detached_layer = NgConnectInterface.instance().detached_editing.layer(
            layer
        )
        keep_existing = (
            self._detached_layer is detached_layer
            and self._feature_id == feature_id
            and self._attachments_model.is_initialized
        )

        self._disconnect_attachment_signals()
        self._loading_generation += 1

        self._detached_layer = detached_layer
        self._feature_id = feature_id

        if not keep_existing:
            self._attachments_model.clear_attachments()
            self._view_wrapper.begin_loading(
                self.tr("Loading attachments"),
                self.tr("Fetching the attachment list."),
            )
        self._add_button.setDisabled(True)
        self._extra_button.setDisabled(True)

        task = IdentificationAttachmentsTask(
            detached_layer,
            feature_id,
            self._loading_generation,
            keep_existing=keep_existing,
        )
        task.taskCompleted.connect(self._on_attachments_task_finished)
        task.taskTerminated.connect(self._on_attachments_task_finished)
        self._attachments_task = task

        NgConnectInterface.instance().task_manager.addTask(task)

    def _connect_attachment_signals(
        self, detached_layer: DetachedLayer
    ) -> None:
        self._disconnect_attachment_signals()

        self._attachment_added_connection = (
            detached_layer.attachment_added.connect(self._on_attachment_added)
        )
        self._attachment_removed_connection = (
            detached_layer.attachment_removed.connect(
                self._on_attachment_removed_from_layer
            )
        )
        self._attachment_updated_connection = (
            detached_layer.attachment_updated.connect(
                self._on_attachment_updated_in_layer
            )
        )

    def clear_feature(self) -> None:
        self._disconnect_attachment_signals()
        self._loading_generation += 1
        self._attachments_task = None
        self._thumbnails_task = None
        self._view_wrapper.end_loading()

        self._detached_layer = None
        self._feature_id = None

        self._attachments_model.clear_attachments()
        self._add_button.setDisabled(True)
        self._extra_button.setDisabled(True)

    def set_read_only(self, read_only: bool) -> None:
        self._is_read_only = read_only
        self._attachments_model.set_editable(not read_only)
        self._add_button.setEnabled(
            not read_only
            and self._feature_id is not None
            and self._attachments_task is None
        )
        self._view_wrapper.set_read_only(read_only)

    def _load_ui(self) -> None:
        layout = QVBoxLayout(self)

        # View wrapper
        self._view_wrapper = AttachmentsViewWrapper(self)
        self._view_wrapper.view.open_attachment.connect(self._open_attachment)
        self._view_wrapper.view.cache_attachment.connect(
            self._cache_attachment
        )
        self._view_wrapper.view.save_as.connect(self._save_attachment_as)
        self._view_wrapper.view.show_in_folder.connect(self._show_in_folder)
        self._view_wrapper.files_dropped.connect(self._add_files)
        layout.addWidget(self._view_wrapper)

        # Buttons row
        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(3)

        self._add_button = QPushButton(self.tr("Add attachment"), self)
        self._add_button.clicked.connect(self._add_attachments)

        icon_color = QgsApplication.palette().text().color().name()
        self._add_button.setIcon(
            material_icon("attach_file_add", color=icon_color)
        )

        self._extra_button = QToolButton(self)
        self._extra_button.setFixedSize(
            self._add_button.sizeHint().height(),
            self._add_button.sizeHint().height(),
        )
        self._extra_button.setStyleSheet(
            """
            QToolButton::menu-indicator {
                image: none;
            }
            """
        )
        self._extra_button.setIcon(
            material_icon("more_horiz", color=icon_color)
        )

        buttons_layout.addWidget(self._add_button)
        buttons_layout.addWidget(self._extra_button)
        layout.addLayout(buttons_layout)

        # Extra menu
        extra_menu = QMenu(self)
        cache_all_action = extra_menu.addAction(
            material_icon("download_for_offline"),
            self.tr("Cache all attachments"),
        )
        cache_all_action.triggered.connect(self._cache_all_attachments)
        extra_menu.addAction(
            qgis_icon("mActionFileSaveAs.svg"),
            self.tr("Save all attachments as..."),
            self._save_all_attachments_as,
        )
        extra_menu.addSeparator()
        sort_menu = extra_menu.addMenu(
            material_icon("sort"), self.tr("Sort By")
        )
        sort_by_name_action = sort_menu.addAction(self.tr("Name"))
        sort_by_name_action.setCheckable(True)
        sort_by_name_action.setChecked(True)
        sort_by_name_action.setData(AttachmentsSortMode.BY_NAME)
        sort_by_type_action = sort_menu.addAction(self.tr("Type"))
        sort_by_type_action.setCheckable(True)
        sort_by_type_action.setData(AttachmentsSortMode.BY_TYPE)
        # sort_by_size_action = sort_menu.addAction(self.tr("Size"))
        # sort_by_size_action.setCheckable(True)
        # sort_by_size_action.setData(AttachmentsSortMode.BY_SIZE)

        sort_menu.addSeparator()

        sort_ascending_action = sort_menu.addAction(self.tr("A-Z"))
        sort_ascending_action.setCheckable(True)
        sort_ascending_action.setChecked(True)
        sort_ascending_action.setData(Qt.SortOrder.AscendingOrder)
        sort_descending_action = sort_menu.addAction(self.tr("Z-A"))
        sort_descending_action.setCheckable(True)
        sort_descending_action.setData(Qt.SortOrder.DescendingOrder)

        sort_by_group = QActionGroup(sort_menu)
        sort_by_group.addAction(sort_by_name_action)
        sort_by_group.addAction(sort_by_type_action)
        # sort_by_group.addAction(sort_by_size_action)
        sort_by_group.setExclusive(True)
        sort_by_group.triggered.connect(self._on_sort_by_changed)

        sort_order_group = QActionGroup(sort_menu)
        sort_order_group.addAction(sort_ascending_action)
        sort_order_group.addAction(sort_descending_action)
        sort_order_group.setExclusive(True)
        sort_order_group.triggered.connect(self._on_sort_order_changed)

        self._extra_button.setMenu(extra_menu)
        self._extra_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )

        # Model
        self._attachments_model = AttachmentsModel([], self)
        self._attachments_model.attachment_removed.connect(
            self._on_attachment_removed_from_model
        )
        self._attachments_model.attachment_updated.connect(
            self._on_attachment_updated_in_model
        )
        self._attachments_proxy = AttachmentsSortProxyModel(self)
        self._attachments_proxy.setSourceModel(self._attachments_model)
        self._attachments_proxy.sort(0, Qt.SortOrder.AscendingOrder)
        self._view_wrapper.view.setModel(self._attachments_proxy)

    def _disconnect_attachment_signals(self) -> None:
        with suppress(RuntimeError, TypeError):
            if self._attachment_added_connection is not None:
                self.disconnect(cast(Any, self._attachment_added_connection))
        self._attachment_added_connection = None

        with suppress(RuntimeError, TypeError):
            if self._attachment_updated_connection is not None:
                self.disconnect(cast(Any, self._attachment_updated_connection))
        self._attachment_updated_connection = None

        with suppress(RuntimeError, TypeError):
            if self._attachment_removed_connection is not None:
                self.disconnect(cast(Any, self._attachment_removed_connection))
        self._attachment_removed_connection = None

    @pyqtSlot()
    def _on_attachments_task_finished(self) -> None:
        task = self.sender()
        if not isinstance(task, IdentificationAttachmentsTask):
            return

        if (
            task is not self._attachments_task
            or task.generation != self._loading_generation
        ):
            return

        self._attachments_task = None

        if task.status() != QgsTask.TaskStatus.Complete:
            if task.keep_existing:
                self._connect_attachment_signals(task.detached_layer)
                self._add_button.setEnabled(not self._is_read_only)
                self._extra_button.setEnabled(True)
            else:
                self._attachments_model.set_attachments([])
                self._add_button.setDisabled(True)
                self._extra_button.setDisabled(True)
            self._view_wrapper.end_loading()
            return

        self._attachments_model.set_attachments(task.attachments)
        self._connect_attachment_signals(task.detached_layer)
        self._add_button.setEnabled(not self._is_read_only)
        self._extra_button.setEnabled(True)
        self._start_thumbnail_loading(task.attachments)

    def _start_thumbnail_loading(
        self, attachments: List[AttachmentMetadata]
    ) -> None:
        detached_layer = self._detached_layer
        if detached_layer is None:
            self._view_wrapper.end_loading()
            return

        connection_id = detached_layer.container.metadata.connection_id
        resource_id = detached_layer.container.metadata.resource_id
        attachments_to_load = [
            attachment
            for attachment in attachments
            if self._should_download_attachment_thumbnail(
                connection_id,
                resource_id,
                attachment,
            )
        ]
        if not attachments_to_load:
            self._view_wrapper.end_loading()
            return

        self._view_wrapper.begin_loading(
            self.tr("Loading previews"),
            self.tr("Fetching image previews."),
        )

        task = AttachmentThumbnailsTask(
            attachments_to_load,
            connection_id,
            resource_id,
            self._loading_generation,
        )
        task.taskCompleted.connect(self._on_thumbnails_task_finished)
        task.taskTerminated.connect(self._on_thumbnails_task_finished)
        self._thumbnails_task = task

        NgConnectInterface.instance().task_manager.addTask(task)

    def _should_download_attachment_thumbnail(
        self,
        connection_id: str,
        resource_id: int,
        attachment: AttachmentMetadata,
    ) -> bool:
        return (
            _needs_attachment_thumbnail_download(attachment)
            and _attachment_thumbnail_key(
                connection_id,
                resource_id,
                attachment,
            )
            not in self._failed_thumbnail_keys
        )

    @pyqtSlot()
    def _on_thumbnails_task_finished(self) -> None:
        task = self.sender()
        if not isinstance(task, AttachmentThumbnailsTask):
            return

        if (
            task is not self._thumbnails_task
            or task.generation != self._loading_generation
        ):
            return

        self._thumbnails_task = None
        self._failed_thumbnail_keys.update(task.failed_thumbnail_keys)

        if (
            task.status() == QgsTask.TaskStatus.Complete
            and task.changed_attachment_ids
        ):
            self._attachments_model.update_cached_states()

        self._view_wrapper.end_loading()

    @pyqtSlot(QgsFeatureId, AttachmentId)
    def _on_attachment_added(
        self, feature_id: QgsFeatureId, attachment_id: AttachmentId
    ) -> None:
        detached_layer = self._detached_layer
        if self._feature_id != feature_id or detached_layer is None:
            return

        new_attachment = detached_layer.feature_attachment(
            feature_id, attachment_id
        )
        assert new_attachment is not None
        self._attachments_model.add_attachment(new_attachment)
        self._start_thumbnail_loading([new_attachment])

    @pyqtSlot(QgsFeatureId, AttachmentId)
    def _on_attachment_updated_in_layer(
        self, feature_id: QgsFeatureId, attachment_id: AttachmentId
    ) -> None:
        detached_layer = self._detached_layer
        if self._feature_id != feature_id or detached_layer is None:
            return

        self._attachments_model.attachment_updated.disconnect(
            self._on_attachment_updated_in_model
        )
        attachment = detached_layer.feature_attachment(
            feature_id, attachment_id
        )
        assert attachment is not None
        self._attachments_model.update_attachment(attachment)
        self._start_thumbnail_loading([attachment])
        self._attachments_model.attachment_updated.connect(
            self._on_attachment_updated_in_model
        )

    @pyqtSlot(QgsFeatureId, AttachmentId)
    def _on_attachment_removed_from_layer(
        self, feature_id: QgsFeatureId, attachment_id: AttachmentId
    ) -> None:
        if self._feature_id != feature_id:
            return

        self._attachments_model.attachment_removed.disconnect(
            self._on_attachment_removed_from_model
        )
        self._attachments_model.remove_attachment(attachment_id)
        self._attachments_model.attachment_removed.connect(
            self._on_attachment_removed_from_model
        )

    @pyqtSlot(AttachmentId)
    def _on_attachment_updated_in_model(
        self, attachment_id: AttachmentId
    ) -> None:
        detached_layer = self._detached_layer
        if detached_layer is None:
            return

        attachment = self._attachments_model.attachment_by_id(attachment_id)
        if attachment is None:
            return

        detached_layer.update_attachment(attachment)

    @pyqtSlot(AttachmentId)
    def _on_attachment_removed_from_model(
        self, attachment_id: AttachmentId
    ) -> None:
        detached_layer = self._detached_layer
        if detached_layer is None or self._feature_id is None:
            return

        detached_layer.remove_attachment(self._feature_id, attachment_id)

    def _add_attachments(self) -> None:
        file_dialog = QFileDialog(self)
        file_dialog.setFileMode(QFileDialog.FileMode.ExistingFiles)
        file_dialog.setNameFilter(self.tr("All Files (*)"))
        file_dialog.setWindowTitle(self.tr("Select Attachments"))

        if file_dialog.exec():
            selected_files = file_dialog.selectedFiles()
            self._add_files(selected_files)

    def _add_files(self, paths: List[str]) -> None:
        detached_layer = self._detached_layer
        if detached_layer is None or self._feature_id is None:
            return

        for file_path in paths:
            path = Path(file_path)
            logger.info(f"Added file: {path}")
            detached_layer.add_attachment(self._feature_id, path)

    @pyqtSlot(QAction)
    def _on_sort_by_changed(self, action: QAction) -> None:  # type: ignore[reportInvalidTypeForm]
        if not action.isChecked():
            return

        sort_key_value = action.data()
        if sort_key_value is None:
            return

        try:
            sort_key = AttachmentsSortMode(sort_key_value)
        except ValueError:
            return

        self._attachments_proxy.sort_key = sort_key

    @pyqtSlot(QAction)
    def _on_sort_order_changed(self, action: QAction) -> None:  # type: ignore[reportInvalidTypeForm]
        if not action.isChecked():
            return

        sort_order = action.data()
        if sort_order not in (
            Qt.SortOrder.AscendingOrder,
            Qt.SortOrder.DescendingOrder,
        ):
            return

        self._attachments_proxy.sort(0, sort_order)

    def _cache_all_attachments(self) -> None:
        detached_layer = self._detached_layer
        if detached_layer is None or self._feature_id is None:
            return

        layer = detached_layer.qgs_layer
        feature = layer.getFeature(self._feature_id)

        context = QgsExpressionContext(
            QgsExpressionContextUtils.globalProjectLayerScopes(layer)
        )
        expression = QgsExpression("ngw_feature_id()")
        expression.prepare(context)
        context.setFeature(feature)
        feature_ngw_fid = expression.evaluate(context)

        resource_id = detached_layer.container.metadata.resource_id
        connection_id = detached_layer.container.metadata.connection_id
        connection = NgwConnectionsManager().connection(connection_id)
        assert connection is not None

        attachments = detached_layer.feature_attachments(self._feature_id)
        attachments_to_download = []

        for attachment in attachments:
            if attachment.ngw_aid is None:
                continue

            attachment_path = detached_layer.attachment_path(
                self._feature_id, attachment.aid
            )
            assert attachment_path is not None
            attachments_to_download.append((attachment, attachment_path))

        if not attachments_to_download:
            return

        with self._attachment_download_overlay(
            self.tr("Downloading attachments"),
            self.tr("Fetching attachment files."),
        ):
            for attachment, attachment_path in attachments_to_download:
                self._download_attachment(
                    connection,
                    resource_id,
                    feature_ngw_fid,
                    attachment.ngw_aid,
                    attachment_path,
                )

        self._attachments_model.update_cached_states()

        logger.debug("Downloaded")

    def _open_attachment(self, index: QModelIndex) -> None:
        attachment: Optional[AttachmentMetadata] = index.data(
            AttachmentsModel.Roles.ATTACHMENT
        )

        if attachment is None:
            return

        self._cache_attachment(index)

        QDesktopServices.openUrl(QUrl.fromLocalFile(str(attachment.file_path)))

    def _show_in_folder(self, index: QModelIndex) -> None:
        attachment: Optional[AttachmentMetadata] = index.data(
            AttachmentsModel.Roles.ATTACHMENT
        )

        if attachment is None:
            return

        assert attachment.file_path is not None
        reveal_in_file_manager(attachment.file_path)

    def _save_attachment_as(self, index: QModelIndex) -> None:
        attachment: Optional[AttachmentMetadata] = index.data(
            AttachmentsModel.Roles.ATTACHMENT
        )

        if attachment is None:
            return

        mime_type_database = QMimeDatabase()
        mime_type = mime_type_database.mimeTypeForName(attachment.mime_type)

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setWindowTitle(self.tr("Save Attachment As"))
        file_dialog.setDefaultSuffix(mime_type.preferredSuffix())
        attachment_name = attachment.name.replace("/", "_").replace("\\", "_")
        attachment_name = attachment_name[:255]
        file_dialog.selectFile(attachment_name)
        file_dialog.setNameFilter(mime_type.filterString())

        if not file_dialog.exec():
            return

        self._cache_attachment(index)

        target_path = Path(file_dialog.selectedFiles()[0])

        assert attachment.file_path is not None
        shutil.copy2(attachment.file_path, target_path)

    def _save_all_attachments_as(self) -> None:
        mime_type_database = QMimeDatabase()
        mime_type = mime_type_database.mimeTypeForName("application/zip")

        file_dialog = QFileDialog(self)
        file_dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave)
        file_dialog.setWindowTitle(self.tr("Save Feature Attachments As"))
        file_dialog.setDefaultSuffix(mime_type.preferredSuffix())
        file_dialog.setNameFilter(mime_type.filterString())

        if not file_dialog.exec():
            return

        self._cache_all_attachments()

        target_path = Path(file_dialog.selectedFiles()[0])
        with ZipFile(target_path, "w", ZIP_DEFLATED) as zipf:
            for row in range(self._attachments_proxy.rowCount()):
                index = self._attachments_proxy.index(row, 0)
                attachment: Optional[AttachmentMetadata] = index.data(
                    AttachmentsModel.Roles.ATTACHMENT
                )
                if attachment is None or not attachment.file_path.exists():
                    continue
                zipf.write(
                    str(attachment.file_path),
                    arcname=(attachment.name or "")[:255],
                )

    def _cache_attachment(self, index: QModelIndex) -> None:
        attachment: Optional[AttachmentMetadata] = index.data(
            AttachmentsModel.Roles.ATTACHMENT
        )

        detached_layer = self._detached_layer
        if detached_layer is None or self._feature_id is None:
            return

        if not attachment or attachment.file_path.exists():
            return

        connection_id = detached_layer.container.metadata.connection_id
        ngw_connection = NgwConnectionsManager().connection(connection_id)
        assert ngw_connection is not None

        with closing(
            make_connection(detached_layer.container.path)
        ) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                """
                SELECT features.ngw_fid, attachments.ngw_aid
                FROM ngw_features_attachments AS attachments
                JOIN ngw_features_metadata AS features
                ON attachments.fid = features.fid
                WHERE attachments.fid = ? AND attachments.aid = ?;
                """,
                (self._feature_id, attachment.aid),
            )
            rows = cursor.fetchall()
            ngw_fid, ngw_aid = rows[0]

        assert attachment.file_path is not None
        with self._attachment_download_overlay(
            self.tr("Downloading attachment"),
            self.tr("Fetching attachment file."),
        ):
            self._download_attachment(
                ngw_connection,
                detached_layer.container.metadata.resource_id,
                ngw_fid,
                ngw_aid,
                attachment.file_path,
            )
        self._attachments_model.update_cached_states()

    @contextmanager
    def _attachment_download_overlay(
        self, title: str, message: str
    ) -> Iterator[None]:
        self._view_wrapper.begin_loading(title, message, delay_ms=0)
        QApplication.processEvents()
        try:
            yield
        finally:
            self._view_wrapper.end_loading()

    def _download_attachment(
        self,
        connection: NgwConnection,
        resource_id: int,
        feature_ngw_fid: str,
        ngw_aid: Union[str, int],
        attachment_path: Path,
    ) -> None:
        url = (
            connection.url + f"/api/resource/{resource_id}"
            f"/feature/{feature_ngw_fid}"
            f"/attachment/{ngw_aid}/download"
        )

        attachment_path.parent.mkdir(parents=True, exist_ok=True)

        ngw_connection = QgsNgwConnection(connection.id)
        ngw_connection.download(url, str(attachment_path))
