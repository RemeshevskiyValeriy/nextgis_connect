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

from nextgis_connect.legacy.detached_editing.detached_editing import (
    DetachedEditing,
)
from nextgis_connect.legacy.notifier.notifier_interface import (
    NotifierInterface,
)
from nextgis_connect.plugin.plugin_container import PluginContainer
from nextgis_connect.plugin.plugin_interface import NgConnectInterface
from nextgis_connect.plugin.processing import init_processing


class NgConnectPlugin(NgConnectInterface):
    """Adapt NextGIS Connect to the QGIS plugin lifecycle.

    Own a plugin container and expose services required by the rest of
    the application through the shared plugin interface.

    :ivar iface: QGIS interface supplied by the plugin host.
    """

    def __init__(self, iface: QgisInterface) -> None:
        """Initialize the plugin adapter.

        :param iface: QGIS interface supplied by the plugin host.
        """
        super().__init__()
        self.iface = iface
        self._container: Optional[PluginContainer] = None

    @property
    def container(self) -> PluginContainer:
        """Return the initialized plugin container.

        :return: Plugin container.
        :raises AssertionError: If the container is not initialized.
        """
        assert self._container is not None, (
            "Plugin container is not initialized"
        )
        return self._container

    def initialize(self) -> None:
        """Initialize the plugin container."""
        self._container = PluginContainer(self, self.iface)

    def initProcessing(self) -> None:
        """Initialize QGIS Processing integration."""
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
        """Return the plugin notifier.

        :return: Notifier interface instance.
        """
        return self.container.notifier

    @property
    def toolbar(self) -> QToolBar:
        """Return the plugin toolbar.

        :return: Plugin toolbar.
        """
        return self.container.toolbar

    @property
    def resource_model(self) -> QAbstractItemModel:
        """Return the resource tree model.

        :return: Resource tree model.
        """
        return self.container.resource_model

    @property
    def resource_selection_model(self) -> QItemSelectionModel:
        """Return the resource selection model.

        :return: Resource selection model.
        """
        return self.container.resource_selection_model

    @property
    def task_manager(self) -> QgsTaskManager:
        """Return the plugin task manager.

        :return: Plugin task manager.
        """
        return self.container.task_manager

    @property
    def detached_editing(self) -> DetachedEditing:
        """Return the detached editing service.

        :return: Detached editing service.
        """
        return self.container.detached_editing

    def synchronize_layers(self) -> None:
        """Schedule detached layer synchronization."""
        QMetaObject.invokeMethod(
            self.detached_editing,
            "synchronizeLayers",
            Qt.ConnectionType.QueuedConnection,
        )

    def enable_synchronization(self) -> None:
        """Enable detached layer synchronization."""
        self.detached_editing.enable_synchronization()
        self.synchronize_layers()

    def disable_synchronization(self) -> None:
        """Disable detached layer synchronization."""
        self.detached_editing.disable_synchronization()
