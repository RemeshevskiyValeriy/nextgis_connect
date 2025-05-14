from typing import cast
from urllib.parse import urlparse

from qgis.PyQt.QtCore import Qt, QVariant
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QTreeWidgetItem

from nextgis_connect.ngw_api.core import (
    NGWGroupResource,
    NGWResource,
)
from nextgis_connect.settings.ng_connect_settings import NgConnectSettings


# TODO: remove QTreeWidgetItem inheritance
class QModelItem(QTreeWidgetItem):
    def __init__(self):
        super().__init__()

        # self.locked_item = ItemBase(["loading..."])
        # self.locked_item.setFlags(Qt.NoItemFlags)

        self._locked = False
        self.unlock()

    def lock(self):
        self._locked = True
        # self.setFlags(Qt.NoItemFlags)
        # self.addChild(self.locked_item)

    @property
    def locked(self):
        return self._locked

    def unlock(self):
        if self._locked:
            # self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            # self.removeChild(self.locked_item)
            self._locked = False

    def flags(self) -> Qt.ItemFlags:
        if self._locked:
            return Qt.ItemFlags() | Qt.ItemFlag.NoItemFlags

        return (
            Qt.ItemFlags()
            | Qt.ItemFlag.ItemIsEnabled
            | Qt.ItemFlag.ItemIsSelectable
        )

    def data(self, role: Qt.ItemDataRole) -> QVariant:
        return QVariant()


class QNGWResourceItem(QModelItem):
    NGWResourceRole = Qt.ItemDataRole.UserRole
    NGWResourceIdRole = Qt.ItemDataRole.UserRole + 1

    _title: str
    _ngw_resource: NGWResource

    def __init__(self, ngw_resource: NGWResource):
        super().__init__()
        title = ngw_resource.display_name

        if (
            ngw_resource.resource_id == 0
            and NgConnectSettings().is_developer_mode
        ):
            server_url = ngw_resource.connection.server_url
            server_url = urlparse(server_url).netloc
            title += f" ({server_url})"

        self._title = title
        self._ngw_resource = ngw_resource
        self._icon = QIcon(self._ngw_resource.icon_path)

    def data(self, role):
        if role == Qt.ItemDataRole.DisplayRole:
            return self._title
        if role == Qt.ItemDataRole.DecorationRole:
            return self._icon
        if role == Qt.ItemDataRole.ToolTipRole and self.ngw_resource_id() == 0:
            return self._ngw_resource.connection.server_url
        if role == QNGWResourceItem.NGWResourceRole:
            return self._ngw_resource
        if role == QNGWResourceItem.NGWResourceIdRole:
            return self._ngw_resource.resource_id
        return super().data(role)

    def ngw_resource_id(self):
        return self.data(QNGWResourceItem.NGWResourceIdRole)

    def is_group(self):
        ngw_resource = cast(NGWResource, self.data(self.NGWResourceRole))
        return ngw_resource.type_id == NGWGroupResource.type_id

    def more_priority(self, item):
        if not isinstance(item, QNGWResourceItem):
            return True

        if self.is_group() != item.is_group():
            return self.is_group() > item.is_group()

        return self._title.lower() < item._title.lower()
