from typing import Optional

from qgis.core import QgsTaskManager
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import (
    QAbstractItemModel,
    QItemSelectionModel,
    QMetaObject,
    Qt,
)
from qgis.PyQt.QtWidgets import QToolBar

from nextgis_connect.bootstrap.plugin_container import PluginContainer
from nextgis_connect.bootstrap.plugin_interface import NgConnectInterface
from nextgis_connect.bootstrap.processing_bootstrap import init_processing
from nextgis_connect.legacy.detached_editing.detached_editing import (
    DetachedEditing,
)
from nextgis_connect.legacy.notifier.notifier_interface import (
    NotifierInterface,
)


class NgConnectPlugin(NgConnectInterface):
    """Thin QGIS lifecycle adapter for NextGIS Connect."""

    def __init__(self, iface: QgisInterface) -> None:
        super().__init__()
        self.iface = iface
        self._container: Optional[PluginContainer] = None

    @property
    def container(self) -> PluginContainer:
        assert self._container is not None, (
            "Plugin container is not initialized"
        )
        return self._container

    def bootstrap(self) -> None:
        self._container = PluginContainer(self, self.iface)

    def initProcessing(self) -> None:
        init_processing(self.container)

    def _load(self) -> None:
        self.container.load()

    def _unload(self) -> None:
        if self._container is None:
            return

        self._container.unload()
        self._container = None

    @property
    def notifier(self) -> "NotifierInterface":
        return self.container.notifier

    @property
    def toolbar(self) -> QToolBar:
        return self.container.toolbar

    @property
    def resource_model(self) -> QAbstractItemModel:
        return self.container.resource_model

    @property
    def resource_selection_model(self) -> QItemSelectionModel:
        return self.container.resource_selection_model

    @property
    def task_manager(self) -> QgsTaskManager:
        return self.container.task_manager

    @property
    def detached_editing(self) -> DetachedEditing:
        return self.container.detached_editing

    def synchronize_layers(self) -> None:
        QMetaObject.invokeMethod(
            self.detached_editing,
            "synchronizeLayers",
            Qt.ConnectionType.QueuedConnection,
        )

    def enable_synchronization(self) -> None:
        self.detached_editing.enable_synchronization()
        self.synchronize_layers()

    def disable_synchronization(self) -> None:
        self.detached_editing.disable_synchronization()
