import configparser
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Generator, Optional
from unittest.mock import MagicMock, Mock

import pytest
import qgis.utils
from qgis.core import (
    QgsApplication,
    QgsLayerTreeModel,
    QgsProject,
    QgsSettings,
)
from qgis.gui import QgisInterface, QgsLayerTreeView, QgsMapCanvas
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QMainWindow, QMenu, QToolBar

PACKAGE_NAME = "nextgis_connect"
WORKSPACE_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = WORKSPACE_ROOT / "src"

if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))


@dataclass(frozen=True)
class ApplicationInfo:
    application: QgsApplication
    qgis_auth_db_path: Path
    qgis_custom_config_path: Path


APPLICATION_INFO: Optional[ApplicationInfo] = None


def _install_plugin_metadata() -> None:
    metadata_path = SOURCE_ROOT / PACKAGE_NAME / "metadata.txt"
    metadata = configparser.ConfigParser()
    with metadata_path.open(encoding="utf-8") as metadata_file:
        metadata.read_file(metadata_file)
    qgis.utils.plugins_metadata_parser[PACKAGE_NAME] = metadata


def start_qgis() -> QgsApplication:
    global APPLICATION_INFO

    if APPLICATION_INFO is not None:
        return APPLICATION_INFO.application

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

    qgis_custom_config_path = Path(
        tempfile.mkdtemp(prefix="TestNextGISConnect-config-")
    )
    qgis_auth_db_path = Path(
        tempfile.mkdtemp(prefix="TestNextGISConnect-authdb-")
    )
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = str(qgis_custom_config_path)
    os.environ["QGIS_AUTH_DB_DIR_PATH"] = str(qgis_auth_db_path)

    QgsApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts,
        True,
    )
    QgsApplication.setOrganizationName("NextGIS_Test")
    QgsApplication.setOrganizationDomain("nextgis.test")
    QgsApplication.setApplicationName("NextGIS Connect Tests")
    QgsSettings().clear()

    application = QgsApplication(list(map(os.fsencode, sys.argv)), True)
    application.initQgis()
    init_interface()
    _install_plugin_metadata()

    APPLICATION_INFO = ApplicationInfo(
        application=application,
        qgis_auth_db_path=qgis_auth_db_path,
        qgis_custom_config_path=qgis_custom_config_path,
    )
    return application


def stop_qgis() -> None:
    if APPLICATION_INFO is None:
        return

    QgsSettings().clear()
    shutil.rmtree(APPLICATION_INFO.qgis_custom_config_path, ignore_errors=True)
    shutil.rmtree(APPLICATION_INFO.qgis_auth_db_path, ignore_errors=True)


def init_interface() -> QgisInterface:
    iface = getattr(qgis.utils, "iface", None)
    if iface is None:
        iface = Mock(spec=QgisInterface)
        qgis.utils.iface = iface

    assert isinstance(iface, Mock)

    main_window = iface.mainWindow.return_value
    if not isinstance(main_window, QMainWindow):
        main_window = QMainWindow()
        iface.mainWindow.return_value = main_window

    map_canvas = iface.mapCanvas.return_value
    if not isinstance(map_canvas, QgsMapCanvas):
        map_canvas = QgsMapCanvas(main_window)
        map_canvas.resize(QSize(400, 400))
        iface.mapCanvas.return_value = map_canvas

    layer_tree_view = iface.layerTreeView.return_value
    if not isinstance(layer_tree_view, QgsLayerTreeView):
        layer_tree_view = QgsLayerTreeView(main_window)
        iface.layerTreeView.return_value = layer_tree_view

    layer_tree_model = QgsLayerTreeModel(
        QgsProject.instance().layerTreeRoot(),
        layer_tree_view,
    )
    layer_tree_view.setModel(layer_tree_model)

    web_menu = iface.webMenu.return_value
    if not isinstance(web_menu, QMenu):
        web_menu = QMenu("Web", main_window)
        iface.webMenu.return_value = web_menu

    plugin_help_menu = iface.pluginHelpMenu.return_value
    if not isinstance(plugin_help_menu, QMenu):
        plugin_help_menu = QMenu("Plugins", main_window)
        iface.pluginHelpMenu.return_value = plugin_help_menu

    new_layer_menu = iface.newLayerMenu.return_value
    if not isinstance(new_layer_menu, QMenu):
        new_layer_menu = QMenu("New Layer", main_window)
        iface.newLayerMenu.return_value = new_layer_menu

    data_source_toolbar = iface.dataSourceManagerToolBar.return_value
    if not isinstance(data_source_toolbar, QToolBar):
        data_source_toolbar = QToolBar(main_window)
        iface.dataSourceManagerToolBar.return_value = data_source_toolbar

    selection_toolbar = iface.selectionToolBar.return_value
    if not isinstance(selection_toolbar, QToolBar):
        selection_toolbar = QToolBar(main_window)
        iface.selectionToolBar.return_value = selection_toolbar

    def add_toolbar(name: str) -> QToolBar:
        toolbar = QToolBar(name, main_window)
        main_window.addToolBar(toolbar)
        return toolbar

    iface.addToolBar.side_effect = add_toolbar

    message_bar = iface.messageBar.return_value
    if not isinstance(message_bar, MagicMock):
        message_bar = MagicMock()
        iface.messageBar.return_value = message_bar
    message_bar.items.return_value = []

    user_profile_manager = iface.userProfileManager.return_value
    if not isinstance(user_profile_manager, MagicMock):
        user_profile = MagicMock()
        user_profile.folder.return_value = tempfile.mkdtemp(
            prefix="TestNextGISConnect-profile-"
        )
        user_profile_manager = MagicMock()
        user_profile_manager.userProfile.return_value = user_profile
        iface.userProfileManager.return_value = user_profile_manager

    return iface


@pytest.fixture(scope="session")
def qgis_app() -> Generator[QgsApplication, None, None]:
    application = start_qgis()
    try:
        yield application
    finally:
        stop_qgis()


@pytest.fixture
def reset_qgis_settings(
    qgis_app: QgsApplication,
) -> Generator[None, None, None]:
    del qgis_app

    settings = QgsSettings()
    settings.clear()
    yield
    settings.clear()


@pytest.fixture
def qgis_iface(
    qgis_app: QgsApplication,
    reset_qgis_settings: None,
) -> QgisInterface:
    del qgis_app, reset_qgis_settings

    iface = init_interface()
    QgsProject.instance().removeAllMapLayers()
    iface.mapCanvas().setLayers([])
    iface.mapCanvas().resize(QSize(400, 400))
    _install_plugin_metadata()
    return iface
