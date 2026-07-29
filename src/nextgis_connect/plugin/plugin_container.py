import sys
from pathlib import Path
from typing import TYPE_CHECKING

from osgeo import gdal
from qgis.core import Qgis, QgsRuntimeProfiler, QgsTaskManager
from qgis.gui import QgisInterface, QgsMessageBarItem
from qgis.PyQt.QtCore import (
    QT_VERSION_STR,
    QAbstractItemModel,
    QCoreApplication,
    QEvent,
    QItemSelectionModel,
    QMetaObject,
    QSysInfo,
    Qt,
)
from qgis.PyQt.QtWidgets import QAction, QToolBar

from nextgis_connect.legacy.detached_editing.detached_editing import (
    DetachedEditing,
)
from nextgis_connect.legacy.notifier.message_bar_notifier import (
    MessageBarNotifier,
)
from nextgis_connect.legacy.notifier.notifier_interface import (
    NotifierInterface,
)
from nextgis_connect.legacy.settings.ng_connect_cache_manager import (
    NgConnectCacheManager,
)
from nextgis_connect.legacy.settings.ui.ng_connect_settings_page import (
    NgConnectOptionsWidgetFactory,
)
from nextgis_connect.legacy.shell.presentation.dock.ng_connect_dock import (
    NgConnectDock,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.compat import LayerType
from nextgis_connect.platform.qgis.errors import (
    NgConnectError,
    NgConnectReloadAfterUpdateWarning,
)
from nextgis_connect.plugin.services import (
    create_detached_editing,
    create_service_container,
    initialize_connections,
    schedule_cache_purging,
)
from nextgis_connect.plugin.translator import initialize_translator
from nextgis_connect.shared.constants import PLUGIN_NAME
from nextgis_connect.shell.presentation.about.about_dialog import AboutDialog
from nextgis_connect.ui_kit.icons import plugin_icon, qgis_icon

if TYPE_CHECKING:
    from nextgis_connect.plugin.plugin_interface import NgConnectInterface


class PluginContainer:
    """Own plugin services and lifecycle wiring.

    Initialize and unload QGIS UI objects, actions, services, detached
    editing, cache maintenance, and notifications in a controlled order.

    :ivar iface: QGIS interface supplied by the plugin host.
    :ivar plugin_dir: Plugin installation directory.
    """

    iface: QgisInterface
    plugin_dir: Path

    def __init__(
        self,
        plugin: "NgConnectInterface",
        iface: QgisInterface,
    ) -> None:
        """Initialize the plugin container.

        :param plugin: Plugin interface instance.
        :param iface: QGIS interface supplied by the plugin host.
        """
        self._plugin = plugin
        self.iface = iface
        self.plugin_dir = plugin.path
        self.__notifier = None
        self.__task_manager = None
        self.__detached_editing = None
        self.__ng_resources_tree_dock = None
        self.__ng_connect_toolbar = None
        self.__show_ngw_resources_tree_action = None
        self.__action_about = None
        self.__show_help_action = None
        self.__options_factory = None
        self.__purge_cache_task = None

        logger.debug("<b>✓ Plugin object created</b>")
        logger.debug(f"<b>ⓘ OS:</b> {QSysInfo().prettyProductName()}")
        logger.debug(f"<b>ⓘ Qt version:</b> {QT_VERSION_STR}")
        logger.debug(f"<b>ⓘ QGIS version:</b> {Qgis.version()}")
        logger.debug(f"<b>ⓘ Python version:</b> {sys.version}")
        logger.debug(f"<b>ⓘ GDAL version:</b> {gdal.__version__}")
        logger.debug(f"<b>ⓘ Plugin version:</b> {self._plugin.version}")
        logger.debug(
            f"<b>ⓘ Plugin path:</b> {self.plugin_dir}"
            + (
                f" -> {self.plugin_dir.resolve()}"
                if self.plugin_dir.is_symlink()
                else ""
            )
        )
        with QgsRuntimeProfiler.profile("Cache migration"):  # type: ignore
            cache_manager = NgConnectCacheManager()
            if cache_manager.need_migration:
                if cache_manager.can_migrate:
                    cache_manager.migrate()
                else:
                    # Cache will be cleared after QGIS restart before any
                    # project is loaded
                    exception = NgConnectReloadAfterUpdateWarning(
                        "Cache migration is not possible"
                    )
                    raise exception

    def load(self) -> None:
        """Load plugin services and user interface objects."""
        with QgsRuntimeProfiler.profile("Plugin initialization"):  # type: ignore
            logger.debug("<b>◴ Start interface initialization</b>...")

            with QgsRuntimeProfiler.profile("Translations initialization"):  # type: ignore
                self.__init_translator()
            with QgsRuntimeProfiler.profile("Notifier initialization"):  # type: ignore
                self.__init_notifier()
            with QgsRuntimeProfiler.profile("Connections intialization"):  # type: ignore
                self.__init_connections()
            with QgsRuntimeProfiler.profile("Task manager initialization"):  # type: ignore
                self.__init_task_manager()
            with QgsRuntimeProfiler.profile("Detached layers initialization"):  # type: ignore
                self.__init_detached_editing()
            with QgsRuntimeProfiler.profile("Dock widget initialization"):  # type: ignore
                self.__init_ng_connect_dock()
            with QgsRuntimeProfiler.profile("Menus initialization"):  # type: ignore
                self.__init_ng_connect_menus()
            with QgsRuntimeProfiler.profile("Actions initialization"):  # type: ignore
                self.__init_ng_layer_actions()
            with QgsRuntimeProfiler.profile("Settings initialization"):  # type: ignore
                self.__init_ng_connect_settings_page()
            with QgsRuntimeProfiler.profile("Cache initialization"):  # type: ignore
                self.__init_cache_purging()

            logger.debug("<b>✓ End plugin initialization</b>")

    def unload(self) -> None:
        """Unload plugin services and user interface objects."""
        logger.debug("<b>Start plugin unloading</b>")

        unload_steps = [
            ("cache purging", self.__unload_cache_purging),
            ("settings page", self.__unload_ng_connect_settings_page),
            ("layer actions", self.__unload_ng_layer_actions),
            ("menus and toolbar", self.__unload_ng_connect_menus),
            ("dock", self.__unload_ng_connect_dock),
            ("detached editing", self.__unload_detached_editing),
            ("task manager", self.__unload_task_manger),
            ("notifier", self.__unload_notifier),
            ("notifications", self.__close_notifications),
        ]
        for step_name, unload_step in unload_steps:
            try:
                unload_step()
            except Exception:
                logger.exception(f"Could not unload {step_name}")

        logger.debug("<b>End plugin unloading</b>")

    @property
    def notifier(self) -> "NotifierInterface":
        """Return the plugin notifier.

        :return: Notifier interface instance.
        :raises AssertionError: If the notifier is not initialized.
        """
        assert self.__notifier is not None, "Notifier is not initialized"
        return self.__notifier

    @property
    def toolbar(self) -> QToolBar:
        """Return the plugin toolbar.

        :return: Plugin toolbar.
        :raises AssertionError: If the toolbar is not initialized.
        """
        assert self.__ng_connect_toolbar is not None
        return self.__ng_connect_toolbar

    @property
    def resource_model(self) -> QAbstractItemModel:
        """Return the resource tree model.

        :return: Resource tree model.
        """
        return self.__ng_resources_tree_dock.resource_model

    @property
    def resource_selection_model(self) -> QItemSelectionModel:
        """Return the resource selection model.

        :return: Resource selection model.
        """
        return None  # type: ignore

    @property
    def task_manager(self) -> QgsTaskManager:
        """Return the plugin task manager.

        :return: Plugin task manager.
        :raises AssertionError: If the task manager is not initialized.
        """
        assert self.__task_manager is not None
        return self.__task_manager

    @property
    def detached_editing(self) -> DetachedEditing:
        """Return the detached editing service.

        :return: Detached editing service.
        :raises AssertionError: If detached editing is not initialized.
        """
        assert self.__detached_editing is not None
        return self.__detached_editing

    def synchronize_layers(self) -> None:
        """Schedule detached layer synchronization."""
        assert self.__detached_editing is not None
        QMetaObject.invokeMethod(
            self.__detached_editing,
            "synchronizeLayers",
            Qt.ConnectionType.QueuedConnection,
        )

    def enable_synchronization(self) -> None:
        """Enable detached layer synchronization."""
        assert self.__detached_editing is not None
        self.__detached_editing.enable_synchronization()
        self.synchronize_layers()

    def disable_synchronization(self) -> None:
        """Disable detached layer synchronization."""
        assert self.__detached_editing is not None
        self.__detached_editing.disable_synchronization()

    def __init_connections(self) -> None:
        initialize_connections()

    def __init_translator(self) -> None:
        initialize_translator(self._plugin, self.plugin_dir)

    def __init_notifier(self) -> None:
        self.__notifier = MessageBarNotifier(self._plugin)

    def __unload_notifier(self) -> None:
        if self.__notifier is None:
            return

        self.__notifier.deleteLater()
        self.__notifier = None

        logger.debug("Notifier unloaded")

    def __close_notifications(self) -> None:
        notifications = self.iface.mainWindow().findChildren(
            QgsMessageBarItem, "NgConnectMessageBarItem"
        )
        for notification in notifications:
            self.iface.messageBar().popWidget(notification)

    def __init_task_manager(self) -> None:
        services = create_service_container()
        assert services.task_manager is not None
        self.__task_manager = services.task_manager
        logger.debug("Task manager initialized")

    def __unload_task_manger(self) -> None:
        if self.__task_manager is None:
            return

        self.__task_manager = None

        logger.debug("Task manager unloaded")

    def __init_detached_editing(self) -> None:
        self.__detached_editing = create_detached_editing()
        self._plugin.connection_updated.connect(
            self.__detached_editing.on_connection_updated,
            type=Qt.ConnectionType.QueuedConnection,  # pyright: ignore[reportCallIssue]
        )
        logger.debug("Detached editing initialized")

    def __unload_detached_editing(self) -> None:
        if self.__detached_editing is None:
            return

        detached_editing = self.__detached_editing
        self.__safe_disconnect(
            self._plugin.connection_updated,
            detached_editing.on_connection_updated,
        )
        detached_editing.unload()
        detached_editing.deleteLater()
        self.__flush_deferred_deletes()
        self.__detached_editing = None

        logger.debug("Detached editing unloaded")

    def __init_ng_connect_dock(self) -> None:
        self.__ng_resources_tree_dock = NgConnectDock(self.iface)
        self.iface.addDockWidget(
            Qt.DockWidgetArea.RightDockWidgetArea,
            self.__ng_resources_tree_dock,
        )

        if self.__detached_editing is None:
            message = "Detached layers mechanism isn't created"
            raise NgConnectError(message)

    def __unload_ng_connect_dock(self) -> None:
        if self.__ng_resources_tree_dock is None:
            return

        dock = self.__ng_resources_tree_dock
        dock.setVisible(False)
        self.iface.removeDockWidget(dock)
        dock.close()
        dock.setParent(None)
        dock.deleteLater()
        self.__flush_deferred_deletes()
        self.__ng_resources_tree_dock = None

    def __init_ng_connect_menus(self) -> None:
        # Show panel action
        self.__ng_connect_toolbar = self.iface.addToolBar(PLUGIN_NAME)
        assert self.__ng_connect_toolbar is not None
        self.__ng_connect_toolbar.setObjectName("NgConnectToolBar")
        self.__ng_connect_toolbar.setToolTip(
            self._plugin.tr("NextGIS Connect Toolbar"),
        )

        self.__show_ngw_resources_tree_action = QAction(
            plugin_icon("branding/connect_logo.svg"),
            self._plugin.tr("Show/Hide NextGIS Connect panel"),
            self.iface.mainWindow(),
        )
        self.__show_ngw_resources_tree_action.setObjectName(
            "NGConnectShowDock",
        )
        self.__show_ngw_resources_tree_action.setEnabled(True)
        self.__show_ngw_resources_tree_action.setCheckable(True)

        self.__show_ngw_resources_tree_action.triggered.connect(
            self.__ng_resources_tree_dock.setUserVisible,
        )
        self.__ng_resources_tree_dock.visibilityChanged.connect(
            self.__show_ngw_resources_tree_action.setChecked,
        )

        self.__ng_connect_toolbar.addAction(
            self.__show_ngw_resources_tree_action,
        )

        self.__action_about = QAction(
            qgis_icon("mActionPropertiesWidget.svg"),
            self._plugin.tr("About plugin..."),
            self.iface.mainWindow(),
        )

        self.__action_about.triggered.connect(self.__open_about)

        # Add action to Web
        self.iface.addPluginToWebMenu(
            PLUGIN_NAME,
            self.__show_ngw_resources_tree_action,
        )
        self.iface.addPluginToWebMenu(
            PLUGIN_NAME,
            self.__action_about,
        )

        for action in self.iface.webMenu().actions():
            if action.text() != PLUGIN_NAME:
                continue
            action.setIcon(plugin_icon("branding/connect_logo.svg"))
            break

        # Add adction to Help > Plugins
        self.__show_help_action = QAction(
            plugin_icon("branding/connect_logo.svg"),
            PLUGIN_NAME,
            self.iface.mainWindow(),
        )
        self.__show_help_action.triggered.connect(self.__open_about)
        plugin_help_menu = self.iface.pluginHelpMenu()
        assert plugin_help_menu is not None
        plugin_help_menu.addAction(self.__show_help_action)

    def __unload_ng_connect_menus(self) -> None:
        if self.__show_ngw_resources_tree_action is not None:
            self.iface.removePluginWebMenu(
                PLUGIN_NAME,
                self.__show_ngw_resources_tree_action,
            )
        if self.__action_about is not None:
            self.iface.removePluginWebMenu(
                PLUGIN_NAME,
                self.__action_about,
            )

        if (
            self.__show_ngw_resources_tree_action is not None
            and self.__ng_resources_tree_dock is not None
        ):
            self.__safe_disconnect(
                self.__show_ngw_resources_tree_action.triggered,
                self.__ng_resources_tree_dock.setUserVisible,
            )
            self.__safe_disconnect(
                self.__ng_resources_tree_dock.visibilityChanged,
                self.__show_ngw_resources_tree_action.setChecked,
            )

        if self.__ng_connect_toolbar is not None:
            toolbar = self.__ng_connect_toolbar
            toolbar.hide()
            self.iface.mainWindow().removeToolBar(toolbar)
            toolbar.setParent(None)
            toolbar.deleteLater()
            self.__flush_deferred_deletes()
        self.__ng_connect_toolbar = None

        if self.__show_ngw_resources_tree_action is not None:
            self.__show_ngw_resources_tree_action.deleteLater()
        self.__show_ngw_resources_tree_action = None
        if self.__action_about is not None:
            self.__action_about.deleteLater()
        self.__action_about = None

        if self.__show_help_action is not None:
            plugin_help_menu = self.iface.pluginHelpMenu()
            assert plugin_help_menu is not None
            plugin_help_menu.removeAction(self.__show_help_action)
            self.__show_help_action.deleteLater()
        self.__show_help_action = None
        self.__flush_deferred_deletes()

    def __init_ng_layer_actions(self) -> None:
        # Tools for NGW communicate
        layer_actions = [
            self.__ng_resources_tree_dock.actionOpenInNGWFromLayer,
            self.__ng_resources_tree_dock.actionOpenLayerHistoryFromLayer,
            self.__ng_resources_tree_dock.layer_menu_separator,
            self.__ng_resources_tree_dock.actionUploadSelectedResources,
            self.__ng_resources_tree_dock.actionUpdateStyle,
            self.__ng_resources_tree_dock.actionAddStyle,
        ]

        for action in layer_actions:
            for layer_type in (LayerType.Vector, LayerType.Raster):
                self.iface.addCustomActionForLayerType(
                    action,
                    PLUGIN_NAME,
                    layer_type,
                    allLayers=True,
                )

        self.iface.newLayerMenu().addAction(
            self.__ng_resources_tree_dock.actionCreateNgwVectorLayer
        )
        self.iface.dataSourceManagerToolBar().addAction(
            self.__ng_resources_tree_dock.actionCreateNgwVectorLayer
        )

    def __unload_ng_layer_actions(self) -> None:
        self.iface.dataSourceManagerToolBar().removeAction(
            self.__ng_resources_tree_dock.actionCreateNgwVectorLayer
        )
        self.iface.newLayerMenu().removeAction(
            self.__ng_resources_tree_dock.actionCreateNgwVectorLayer
        )

        layer_actions = [
            self.__ng_resources_tree_dock.actionOpenInNGWFromLayer,
            self.__ng_resources_tree_dock.actionOpenLayerHistoryFromLayer,
            self.__ng_resources_tree_dock.layer_menu_separator,
            self.__ng_resources_tree_dock.actionUploadSelectedResources,
            self.__ng_resources_tree_dock.actionUpdateStyle,
            self.__ng_resources_tree_dock.actionAddStyle,
        ]
        for action in layer_actions:
            # For vector and raster types
            self.iface.removeCustomActionForLayerType(action)
            self.iface.removeCustomActionForLayerType(action)

    def __init_ng_connect_settings_page(self) -> None:
        self.__options_factory = NgConnectOptionsWidgetFactory()
        self.iface.registerOptionsWidgetFactory(self.__options_factory)

    def __unload_ng_connect_settings_page(self) -> None:
        if self.__options_factory is None:
            return

        self.iface.unregisterOptionsWidgetFactory(self.__options_factory)
        self.__options_factory.deleteLater()
        self.__options_factory = None

    def __init_cache_purging(self) -> None:
        self.__purge_cache_task = schedule_cache_purging()

    def __unload_cache_purging(self) -> None:
        purge_cache_task = getattr(
            self,
            "_PluginContainer__purge_cache_task",
            None,
        )
        if purge_cache_task is None:
            return

        purge_cache_task.cancel()
        purge_cache_task.waitForFinished(1000)
        self.__purge_cache_task = None

    def __open_about(self) -> None:
        dialog = AboutDialog(
            str(self.plugin_dir.name),
            components_path=self.plugin_dir / "assets" / "components.json",
        )
        dialog.exec()

    def __safe_disconnect(self, signal, slot) -> None:
        try:
            signal.disconnect(slot)
        except (RuntimeError, TypeError):
            pass

    def __flush_deferred_deletes(self) -> None:
        QCoreApplication.sendPostedEvents(
            None,
            QEvent.Type.DeferredDelete,
        )
