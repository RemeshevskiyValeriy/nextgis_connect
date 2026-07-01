import shutil
from contextlib import closing, suppress
from pathlib import Path
from typing import Any, List, Optional, Union, cast
from zipfile import ZIP_DEFLATED, ZipFile

from qgis.core import (
    QgsApplication,
    QgsExpression,
    QgsExpressionContext,
    QgsExpressionContextUtils,
    QgsVectorLayer,
)
from qgis.PyQt.QtCore import (
    QMimeDatabase,
    QModelIndex,
    Qt,
    QUrl,
    pyqtSlot,
)
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction,
    QActionGroup,
    QFileDialog,
    QHBoxLayout,
    QListView,
    QMenu,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from nextgis_connect.compat import QgsFeatureId
from nextgis_connect.detached_editing.detached_layer import DetachedLayer
from nextgis_connect.detached_editing.identification.attachments_model import (
    AttachmentsModel,
)
from nextgis_connect.detached_editing.identification.attachments_sort_proxy_model import (
    AttachmentsSortMode,
    AttachmentsSortProxyModel,
)
from nextgis_connect.detached_editing.identification.ui.attachments_view_wrapper import (
    AttachmentsViewWrapper,
)
from nextgis_connect.detached_editing.utils import (
    AttachmentMetadata,
    make_connection,
)
from nextgis_connect.logging import logger
from nextgis_connect.ng_connect_interface import NgConnectInterface
from nextgis_connect.ngw_api.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.ngw_connection import NgwConnection, NgwConnectionsManager
from nextgis_connect.shared.utils.filesystem import reveal_in_file_manager
from nextgis_connect.types import AttachmentId
from nextgis_connect.ui.icon import material_icon, qgis_icon


class AttachmentsTab(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        self._detached_layer: Optional[DetachedLayer] = None
        self._feature_id: Optional[QgsFeatureId] = None

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
        self._disconnect_attachment_signals()

        detached_layer = NgConnectInterface.instance().detached_editing.layer(
            layer
        )

        self._detached_layer = detached_layer
        self._feature_id = feature_id

        self._attachments_model.set_attachments(
            detached_layer.feature_attachments(feature_id)
        )

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

        self._extra_button.setEnabled(True)

    def clear_feature(self) -> None:
        self._disconnect_attachment_signals()

        self._detached_layer = None
        self._feature_id = None

        self._attachments_model.clear_attachments()
        self._extra_button.setDisabled(True)

    def set_read_only(self, read_only: bool) -> None:
        self._attachments_model.set_editable(not read_only)
        self._add_button.setEnabled(not read_only)
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

    @pyqtSlot(QgsFeatureId, AttachmentId)
    def _on_attachment_added(
        self, feature_id: QgsFeatureId, attachment_id: AttachmentId
    ) -> None:
        detached_layer = self._detached_layer
        if self._feature_id != feature_id or detached_layer is None:
            return

        self._attachments_model.attachment_added.disconnect(
            self._on_attachment_added
        )
        new_attachment = detached_layer.feature_attachment(
            feature_id, attachment_id
        )
        assert new_attachment is not None
        self._attachments_model.add_attachment(new_attachment)
        self._attachments_model.attachment_added.connect(
            self._on_attachment_added
        )

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

        for attachment in attachments:
            if attachment.ngw_aid is None:
                continue

            attachment_path = detached_layer.attachment_path(
                self._feature_id, attachment.aid
            )
            assert attachment_path is not None

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
        self._download_attachment(
            ngw_connection,
            detached_layer.container.metadata.resource_id,
            ngw_fid,
            ngw_aid,
            attachment.file_path,
        )
        self._attachments_model.update_cached_states()

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
