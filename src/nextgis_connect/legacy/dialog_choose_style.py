from typing import Optional

from qgis.PyQt.QtCore import (
    QAbstractItemModel,
    QModelIndex,
    QSortFilterProxyModel,
    Qt,
    pyqtSignal,
)
from qgis.PyQt.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QSizePolicy,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from nextgis_connect.legacy.ngw.core.ngw_abstract_vector_resource import (
    NGWAbstractVectorResource,
)
from nextgis_connect.legacy.ngw.core.ngw_qgis_style import (
    NGWQGISStyle,
)
from nextgis_connect.legacy.ngw.core.ngw_raster_layer import NGWRasterLayer
from nextgis_connect.legacy.tree_widget import QNGWResourceItem


class NGWResourcesTreeView(QTreeView):
    itemDoubleClicked = pyqtSignal(QModelIndex)

    def __init__(self, parent):
        super().__init__(parent)
        self.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )
        self.setHeaderHidden(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        header = self.header()
        header.setStretchLastSection(True)
        header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

    def mouseDoubleClickEvent(self, e):
        index = self.indexAt(e.pos())
        if index.isValid():
            self.itemDoubleClicked.emit(index)

        super().mouseDoubleClickEvent(e)


class StyleFilterProxyModel(QSortFilterProxyModel):
    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        if index is None or not index.isValid():
            return False
        ngw_resource = index.data(QNGWResourceItem.NGWResourceRole)
        return isinstance(
            ngw_resource,
            (
                NGWQGISStyle,
                NGWAbstractVectorResource,
                NGWRasterLayer,  # must also be included here so styles could be displayed
            ),
        )


class NGWLayerStyleChooserDialog(QDialog):
    def __init__(
        self,
        title: str,
        ngw_resources_model_index: QModelIndex,
        model: QAbstractItemModel,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)

        self.__sort_model = StyleFilterProxyModel(self)
        self.__sort_model.setSourceModel(model)
        self.__sort_model.setRecursiveFilteringEnabled(True)

        self.__layout = QVBoxLayout(self)
        self.tree = NGWResourcesTreeView(self)
        self.tree.setModel(self.__sort_model)
        self.tree.setRootIndex(
            self.__sort_model.mapFromSource(ngw_resources_model_index)
        )
        self.tree.selectionModel().selectionChanged.connect(self.validate)
        self.__layout.addWidget(self.tree)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            Qt.Orientation.Horizontal,
            self,
        )
        self.btn_box.button(
            QDialogButtonBox.StandardButton.Ok
        ).clicked.connect(self.accept)
        self.btn_box.button(
            QDialogButtonBox.StandardButton.Cancel
        ).clicked.connect(self.reject)
        self.__layout.addWidget(self.btn_box)

        self.tree.itemDoubleClicked.connect(self.accept)

        self.validate()

    def selectedStyleIndex(self):
        proxy_index = self.tree.selectionModel().currentIndex()
        if proxy_index is None or not proxy_index.isValid():
            return None
        return self.__sort_model.mapToSource(proxy_index)

    def selectedStyle(self):
        selected_index = self.selectedStyleIndex()
        if selected_index is None or not selected_index.isValid():
            return None
        return selected_index.internalPointer()

    def selectedStyleId(self):
        item = self.selectedStyle()
        if item is None:
            return None
        return item.ngw_resource_id()

    def validate(self):
        index = self.selectedStyleIndex()
        self.btn_box.button(QDialogButtonBox.StandardButton.Ok).setEnabled(
            index is not None and index.isValid()
        )
