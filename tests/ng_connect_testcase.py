import atexit
import gc
import json
import os
import sys
import tempfile
import uuid
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Any, ClassVar, Dict, List, Optional, Union
from unittest.mock import MagicMock, Mock

import qgis.utils
from qgis.core import (
    QgsApplication,
    QgsAuthMethodConfig,
    QgsLayerTreeModel,
    QgsMapLayer,
    QgsProject,
    QgsSettings,
    QgsVectorLayer,
)
from qgis.gui import QgisInterface, QgsLayerTreeView, QgsMapCanvas
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.testing import QgisTestCase

from nextgis_connect.legacy.ngw_connection import (
    NgwConnection,
    NgwConnectionsManager,
)
from nextgis_connect.ngw.core import NGWResource
from nextgis_connect.ngw.core.ngw_resource_factory import (
    NGWResourceFactory,
)
from nextgis_connect.ngw.qgis.qgis_ngw_connection import QgsNgwConnection
from nextgis_connect.platform.filesystem import rm


class TestData(str, Enum):
    Points = "layers/points_layer.gpkg"

    def __str__(self) -> str:
        return str(self.value)


class TestConnection(Enum):
    SandboxGuest = auto()
    SandboxWithLogin = auto()
    DemoGuest = auto()
    # UserWithEmail = auto()
    # UserWithOAuth = auto()
    # UserWithNgStd = auto()


@dataclass
class ApplicationInfo:
    APPLICATION_NAME = "TestNextGISConnect"
    ORGANIZATION_NAME = "NextGIS_Test"
    ORGANIZATION_DOMAIN = "TestNextGISConnect.com"

    application: QgsApplication
    qgis_custom_config_path: Path
    qgis_auth_db_path: Path


APPLICATION_INFO: Optional[ApplicationInfo] = None


class NgConnectTestCase(QgisTestCase):
    _connections_id: ClassVar[Dict[TestConnection, str]] = {}
    _temp_paths: ClassVar[List[Path]]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls._temp_paths = []
        start_qgis()

    @classmethod
    def tearDownClass(cls):
        QgsSettings().clear()
        cls._clear_auth_configs()

        for path in cls._temp_paths:
            rm(path)

        super().tearDownClass()

    @classmethod
    def _clear_auth_configs(cls) -> None:
        auth_manager = QgsApplication.authManager()
        for config_id in list(auth_manager.availableAuthMethodConfigs()):
            if config_id == "NextGIS":
                continue
            auth_manager.removeAuthenticationConfig(config_id)

    @classmethod
    def create_temp_file(cls, suffix: str = "") -> Path:
        path = Path(
            tempfile.mktemp(
                prefix=f"{ApplicationInfo.APPLICATION_NAME}-", suffix=suffix
            )
        )
        cls._temp_paths.append(path)
        return path

    @classmethod
    def create_temp_dir(cls, suffix: str = "") -> Path:
        path = Path(
            tempfile.mkdtemp(
                prefix=f"{ApplicationInfo.APPLICATION_NAME}-", suffix=suffix
            )
        )
        cls._temp_paths.append(path)
        return path

    @staticmethod
    def data_path(test_data: TestData) -> Path:
        return Path(__file__).parent / "test_data" / str(test_data)

    @staticmethod
    def layer_uri(test_data: TestData) -> str:
        assert str(test_data).startswith("layers")

        data_path = NgConnectTestCase.data_path(test_data)
        if not data_path.suffix == ".gpkg":
            return str(data_path)

        return f"{data_path}|layername={data_path.stem}"

    @staticmethod
    def layer(test_data: TestData) -> QgsMapLayer:
        if str(test_data).endswith(("gpkg", "shp")):
            return QgsVectorLayer(
                NgConnectTestCase.layer_uri(test_data),
                Path(str(test_data)).stem,
                "ogr",
            )

        raise NotImplementedError

    @staticmethod
    def resource_json(
        test_data: TestData,
    ) -> Dict[str, Any]:
        data_path = NgConnectTestCase.data_path(test_data)
        json_path = data_path.with_suffix(".json")
        return json.loads(json_path.read_text())

    @staticmethod
    def resource(
        test_data: Union[TestData, Dict[str, Any]],
        test_connection: Union[
            TestConnection, NgwConnection
        ] = TestConnection.SandboxGuest,
    ) -> NGWResource:
        if isinstance(test_data, TestData):
            resource_json = NgConnectTestCase.resource_json(test_data)
        else:
            resource_json = test_data

        if isinstance(test_connection, TestConnection):
            connection = NgConnectTestCase.connection(test_connection)
        else:
            connection = test_connection

        ngw_connection = MagicMock(spec=QgsNgwConnection)
        ngw_connection.connection_id = connection.id
        ngw_connection.server_url = connection.url

        factory = NGWResourceFactory(ngw_connection)
        return factory.get_resource_by_json(resource_json)

    @classmethod
    def connection_id(cls, test_connection: TestConnection) -> str:
        cls._init_connections()
        return cls._connections_id[test_connection]

    @classmethod
    def connection(cls, test_connection: TestConnection) -> NgwConnection:
        cls._init_connections()

        connections_manager = NgwConnectionsManager()
        connection = connections_manager.connection(
            cls._connections_id[test_connection]
        )
        assert connection is not None
        return connection

    @classmethod
    def _init_connections(cls) -> None:
        connections_manager = NgwConnectionsManager()
        auth_manager = QgsApplication.authManager()

        def upsert_test_connection(
            test_connection: TestConnection,
            name: str,
            url: str,
            auth_config_id: Optional[str],
        ) -> None:
            connection_id = cls._connections_id.get(
                test_connection, str(uuid.uuid4())
            )
            expected_connection = NgwConnection(
                connection_id,
                name,
                url,
                auth_config_id,
            )
            if (
                connections_manager.connection(connection_id)
                != expected_connection
            ):
                connections_manager.upsert(expected_connection)

            cls._connections_id[test_connection] = connection_id

        upsert_test_connection(
            TestConnection.SandboxGuest,
            "TEST_SANDBOX_GUEST_CONNECTION",
            "https://sandbox.nextgis.com/",
            None,
        )

        basic_connection_id = cls._connections_id.get(
            TestConnection.SandboxWithLogin
        )
        basic_connection = (
            connections_manager.connection(basic_connection_id)
            if basic_connection_id is not None
            else None
        )
        basic_auth_config_id = (
            basic_connection.auth_config_id
            if basic_connection is not None
            else None
        )
        if (
            basic_auth_config_id is None
            or basic_auth_config_id
            not in auth_manager.availableAuthMethodConfigs()
        ):
            auth_config = QgsAuthMethodConfig("Basic")
            auth_config.setName("test_auth_config")
            auth_config.setConfig("username", "administrator")
            auth_config.setConfig("password", "demodemo")
            assert auth_manager.storeAuthenticationConfig(auth_config)[0]
            basic_auth_config_id = auth_config.id()

        upsert_test_connection(
            TestConnection.SandboxWithLogin,
            "TEST_SANDBOX_LOGIN_CONNECTION",
            "https://sandbox-login.nextgis.com/",
            basic_auth_config_id,
        )

        upsert_test_connection(
            TestConnection.DemoGuest,
            "TEST_DEMO_GUEST_CONNECTION",
            "https://demo.nextgis.com/",
            None,
        )

        connections_manager.save()


def start_qgis() -> None:
    """
    Will start a QgsApplication and call all initialization code like
    registering the providers and other infrastructure. It will not load
    any plugins.

    You can always get the reference to a running app by calling `QgsApplication.instance()`.

    The initialization will only happen once, so it is safe to call this method repeatedly.
    """
    global APPLICATION_INFO

    if APPLICATION_INFO is not None:
        return

    existing_application = QgsApplication.instance()
    if existing_application is not None:
        qgis_custom_config_path = Path(os.environ["QGIS_CUSTOM_CONFIG_PATH"])
        qgis_auth_db_path = Path(os.environ["QGIS_AUTH_DB_DIR_PATH"])
        APPLICATION_INFO = ApplicationInfo(
            application=existing_application,
            qgis_custom_config_path=qgis_custom_config_path,
            qgis_auth_db_path=qgis_auth_db_path,
        )

        init_interface()

        auth_manager = QgsApplication.authManager()
        assert not auth_manager.isDisabled(), auth_manager.disabledMessage()
        assert (
            Path(auth_manager.authenticationDatabasePath())
            == APPLICATION_INFO.qgis_auth_db_path / "qgis-auth.db"
        )
        assert auth_manager.setMasterPassword("masterpassword", True)
        return

    qgis_custom_config_path = tempfile.mkdtemp(
        prefix=f"{ApplicationInfo.APPLICATION_NAME}-config-"
    )
    qgis_auth_db_path = tempfile.mkdtemp(
        prefix=f"{ApplicationInfo.APPLICATION_NAME}-authdb-"
    )
    os.environ["QGIS_CUSTOM_CONFIG_PATH"] = qgis_custom_config_path
    os.environ["QGIS_AUTH_DB_DIR_PATH"] = qgis_auth_db_path

    # Application params
    QgsApplication.setAttribute(
        Qt.ApplicationAttribute.AA_ShareOpenGLContexts, True
    )

    # Tests params
    QgsApplication.setOrganizationName(ApplicationInfo.ORGANIZATION_NAME)
    QgsApplication.setOrganizationDomain(ApplicationInfo.ORGANIZATION_DOMAIN)
    QgsApplication.setApplicationName(ApplicationInfo.APPLICATION_NAME)
    QgsSettings().clear()

    # In python3 we need to convert to a bytes object (or should
    # QgsApplication accept a QString instead of const char* ?)
    argvb = list(map(os.fsencode, sys.argv))

    # Note: QGIS_PREFIX_PATH is evaluated in QgsApplication -
    # no need to mess with it here.
    application = QgsApplication(argvb, GUIenabled=True)

    # Save application info
    APPLICATION_INFO = ApplicationInfo(
        application=application,
        qgis_custom_config_path=Path(qgis_custom_config_path),
        qgis_auth_db_path=Path(qgis_auth_db_path),
    )

    # Initialize qgis
    application.initQgis()

    init_interface()

    # Setup logging
    def print_log_message(message, tag, level):
        print(f"{tag}({level}): {message}")  # noqa: T201

    QgsApplication.instance().messageLog().messageReceived.connect(
        print_log_message
    )

    # Setup auth manager
    auth_manager = QgsApplication.authManager()
    assert not auth_manager.isDisabled(), auth_manager.disabledMessage()
    assert (
        Path(auth_manager.authenticationDatabasePath())
        == APPLICATION_INFO.qgis_auth_db_path / "qgis-auth.db"
    )
    assert auth_manager.setMasterPassword("masterpassword", True)

    # print(QGISAPP.showSettings())

    atexit.register(stop_qgis)


def stop_qgis() -> None:
    """
    Cleans up and exits QGIS
    """

    if APPLICATION_INFO is None:
        return

    for _ in range(3):
        gc.collect()
        QgsApplication.processEvents()

    APPLICATION_INFO.application.exitQgis()
    del APPLICATION_INFO.application

    rm(APPLICATION_INFO.qgis_custom_config_path)
    rm(APPLICATION_INFO.qgis_auth_db_path)

    for path in Path(tempfile.gettempdir()).glob(
        f"{ApplicationInfo.APPLICATION_NAME}*"
    ):
        rm(path)


def init_interface() -> None:
    iface = getattr(qgis.utils, "iface", None)
    if iface is None:
        iface = Mock(spec=QgisInterface)
        qgis.utils.iface = iface

    assert isinstance(iface, Mock)

    iface.mainWindow.return_value = QMainWindow()

    canvas = QgsMapCanvas(iface.mainWindow())
    canvas.resize(QSize(400, 400))
    iface.mapCanvas.return_value = canvas

    layer_tree_view = QgsLayerTreeView(iface.mainWindow())
    layer_tree_model = QgsLayerTreeModel(
        QgsProject.instance().layerTreeRoot(), layer_tree_view
    )
    layer_tree_view.setModel(layer_tree_model)
    iface.layerTreeView.return_value = layer_tree_view

    user_profile = MagicMock()
    user_profile.folder.return_value = tempfile.mkdtemp(
        prefix=f"{ApplicationInfo.APPLICATION_NAME}-profile-"
    )
    user_profile_manager = MagicMock()
    user_profile_manager.userProfile.return_value = user_profile
    iface.userProfileManager.return_value = user_profile_manager
