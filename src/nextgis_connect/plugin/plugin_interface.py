import configparser
from abc import abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING

from qgis import utils
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QObject, QTranslator, pyqtSignal

from nextgis_connect.platform.logging import logger, unload_logger
from nextgis_connect.platform.qt import QObjectMetaClass
from nextgis_connect.shared.constants import PACKAGE_NAME

if TYPE_CHECKING:
    from qgis.core import QgsTaskManager
    from qgis.PyQt.QtCore import QAbstractItemModel, QItemSelectionModel
    from qgis.PyQt.QtWidgets import QToolBar

    from nextgis_connect.legacy.detached_editing.detached_editing import (
        DetachedEditing,
    )
    from nextgis_connect.legacy.notifier.notifier_interface import (
        NotifierInterface,
    )


class NgConnectInterface(QObject, metaclass=QObjectMetaClass):
    """Define the shared NextGIS Connect plugin interface.

    Expose plugin metadata, lifecycle hooks, UI services, detached
    editing services, and shared synchronization signals.

    :ivar settings_changed: Signal emitted when plugin settings change.
    :ivar connection_updated: Signal emitted when a connection changes.
    """

    settings_changed = pyqtSignal()
    connection_updated = pyqtSignal(str, object)

    @classmethod
    def instance(cls) -> "NgConnectInterface":
        """Return the registered plugin instance.

        :return: Registered plugin instance.
        :raises AssertionError: If the plugin instance is not yet created.
        """
        plugin = utils.plugins.get(PACKAGE_NAME)
        assert plugin is not None, "Using a plugin before it was created"
        return plugin

    @property
    def metadata(self) -> configparser.ConfigParser:
        """Return plugin metadata.

        :return: Parsed plugin metadata.
        :raises AssertionError: If the plugin metadata is not available.
        """
        metadata = utils.plugins_metadata_parser.get(PACKAGE_NAME)
        assert metadata is not None, "Using a plugin before it was created"
        return metadata

    @property
    def version(self) -> str:
        """Return the plugin version.

        :return: Plugin version string.
        """
        return self.metadata.get("general", "version")

    @property
    def path(self) -> "Path":
        """Return the plugin path.

        :return: Plugin directory path.
        """
        return Path(__file__).resolve().parents[1]

    @property
    @abstractmethod
    def toolbar(self) -> "QToolBar":
        """Return the plugin toolbar.

        :return: Plugin toolbar.
        """
        ...

    @property
    @abstractmethod
    def resource_model(self) -> "QAbstractItemModel":
        """Return the resource tree model.

        :return: Resource tree model.
        """
        ...

    @property
    @abstractmethod
    def resource_selection_model(self) -> "QItemSelectionModel":
        """Return the resource selection model.

        :return: Resource selection model.
        """
        ...

    @property
    @abstractmethod
    def task_manager(self) -> "QgsTaskManager":
        """Return the plugin task manager.

        :return: Plugin task manager.
        """
        ...

    @property
    @abstractmethod
    def detached_editing(self) -> "DetachedEditing":
        """Return the detached editing service.

        :return: Detached editing service.
        """
        ...

    @abstractmethod
    def synchronize_layers(self) -> None:
        """Schedule detached layer synchronization."""
        ...

    @abstractmethod
    def enable_synchronization(self) -> None:
        """Enable detached layer synchronization."""
        ...

    @abstractmethod
    def disable_synchronization(self) -> None:
        """Disable detached layer synchronization."""
        ...

    @property
    @abstractmethod
    def notifier(self) -> "NotifierInterface":
        """Return the plugin notifier.

        :return: Notifier interface instance.
        """
        ...

    def initGui(self) -> None:
        """Initialize plugin GUI components."""
        self.__translators = list()

        try:
            self._load()
        except Exception:
            logger.exception("An error occurred while plugin loading")

    def unload(self) -> None:
        """Unload plugin components."""
        try:
            self._unload()
        except Exception:
            logger.exception("An error occurred while plugin unloading")

        self.__unload_translations()
        unload_logger()

    @abstractmethod
    def _load(self) -> None:
        """Load plugin resources and components."""
        ...

    @abstractmethod
    def _unload(self) -> None:
        """Unload plugin resources and components."""
        ...

    def _add_translator(self, translator_path: Path) -> None:
        """Add a translator for the plugin.

        :param translator_path: Path to the translation file.
        """
        translator = QTranslator()
        is_loaded = translator.load(str(translator_path))
        if not is_loaded:
            logger.debug(f"Translator {translator_path} wasn't loaded")
            return

        is_installed = QgsApplication.installTranslator(translator)
        if not is_installed:
            logger.error(f"Translator {translator_path} wasn't installed")
            return

        # Should be kept in memory
        self.__translators.append(translator)

    def __unload_translations(self) -> None:
        """Remove all translators added by the plugin."""
        for translator in self.__translators:
            QgsApplication.removeTranslator(translator)
        self.__translators.clear()
