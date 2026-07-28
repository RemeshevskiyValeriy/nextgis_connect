import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from qgis.core import QgsApplication, QgsAuthMethodConfig
from qgis.PyQt.QtCore import QSettings

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)


class NgwConnectionSettingsMigrator:
    def migrate(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
    ) -> Tuple[List[NgwConnection], Optional[str], bool]:
        old_connections, old_current_connection_id, old_changed = (
            self.convert_old_connections(connections, current_connection_id)
        )
        merged_connections, merged_current_connection_id, merge_changed = (
            self.merge_duplicate_web_gis_connections(
                old_connections,
                old_current_connection_id,
            )
        )

        return (
            merged_connections,
            merged_current_connection_id,
            old_changed or merge_changed,
        )

    def has_not_converted_connections(
        self,
        existing_connections: List[NgwConnection],
    ) -> bool:
        old_connections = self.__old_connection_names()
        converted_connections = {
            connection.name for connection in existing_connections
        }
        return len(set(old_connections) - converted_connections) > 0

    def convert_old_connections(
        self,
        existing_connections: List[NgwConnection],
        current_connection_id: Optional[str],
        *,
        convert_auth: bool = True,
    ) -> Tuple[List[NgwConnection], Optional[str], bool]:
        old_settings = QSettings("NextGIS", "NextGIS WEB API")
        selected_name = old_settings.value(
            "/ui/selectedConnection", "", type=str
        )
        old_connection_names = self.__old_connection_names()
        converted_connection_names = {
            connection.name for connection in existing_connections
        }

        connections = list(existing_connections)
        new_current_connection_id = current_connection_id
        changed = False

        for old_connection_name in old_connection_names:
            if old_connection_name in converted_connection_names:
                continue

            connection_id = str(uuid.uuid4())
            key = "/connections/" + old_connection_name
            url = old_settings.value(key + "/server_url", "", type=str)
            username = old_settings.value(key + "/username", "", type=str)
            password = old_settings.value(key + "/password", "", type=str)
            is_oauth = old_settings.value(key + "/oauth", "", type=bool)

            auth_config_id = None
            if is_oauth:
                auth_config_id = "NextGIS"
            elif convert_auth:
                auth_config_id = self.__save_auth_method(
                    old_connection_name,
                    NgwConnection.normalize_url(url),
                    username,
                    password,
                )

            connections.append(
                NgwConnection(
                    connection_id, old_connection_name, url, auth_config_id
                )
            )
            converted_connection_names.add(old_connection_name)
            changed = True

            if selected_name == old_connection_name:
                new_current_connection_id = connection_id

        if changed:
            self.clear_old_connections_if_converted(connections)

        return connections, new_current_connection_id, changed

    def clear_old_connections_if_converted(
        self,
        existing_connections: List[NgwConnection],
    ) -> None:
        if self.has_not_converted_connections(existing_connections):
            return

        old_settings = QSettings("NextGIS", "NextGIS WEB API")
        settings_path = Path(old_settings.fileName())
        if settings_path.exists() and settings_path.is_file():
            old_settings = None
            settings_path.unlink()
            return

        old_settings.clear()

    def merge_duplicate_web_gis_connections(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
    ) -> Tuple[List[NgwConnection], Optional[str], bool]:
        grouped_connections: Dict[str, List[NgwConnection]] = {}
        for connection in connections:
            normalized_url = NgwConnection.normalize_url(connection.url)
            group_key = normalized_url
            if len(normalized_url.strip()) == 0:
                group_key = f"empty:{connection.id}"
            grouped_connections.setdefault(group_key, []).append(connection)

        changed = False
        merged_connections = []
        new_current_connection_id = current_connection_id

        for normalized_url, url_connections in grouped_connections.items():
            if len(url_connections) == 1:
                connection = url_connections[0]
                self.ensure_auth_resource(
                    connection.auth_config_id, normalized_url
                )
                merged_connections.append(connection)
                continue

            changed = True
            active_connection = next(
                (
                    connection
                    for connection in url_connections
                    if connection.id == current_connection_id
                ),
                None,
            )
            kept_connection = active_connection or url_connections[0]
            merged_connections.append(kept_connection)
            if active_connection is not None:
                new_current_connection_id = kept_connection.id

            for connection in url_connections:
                self.ensure_auth_resource(
                    connection.auth_config_id, normalized_url
                )

        return merged_connections, new_current_connection_id, changed

    def ensure_auth_resource(
        self,
        auth_config_id: Optional[str],
        resource: str,
    ) -> bool:
        if auth_config_id is None or auth_config_id == "NextGIS":
            return False

        normalized_resource = NgwConnection.normalize_url(resource)
        if len(normalized_resource.strip()) == 0:
            return False

        auth_manager = QgsApplication.authManager()
        if auth_manager.configAuthMethodKey(auth_config_id) != "Basic":
            return False

        method_config = QgsAuthMethodConfig()
        if not auth_manager.loadAuthenticationConfig(
            auth_config_id,
            method_config,
            True,
        ):
            return False

        if method_config.uri().strip() != "":
            return False

        method_config.setUri(normalized_resource)
        return auth_manager.updateAuthenticationConfig(method_config)

    def remove_auth_if_unused(
        self,
        auth_config_id: Optional[str],
        remaining_connections: List[NgwConnection],
    ) -> bool:
        if auth_config_id is None or auth_config_id == "NextGIS":
            return False

        for connection in remaining_connections:
            if connection.auth_config_id == auth_config_id:
                return False

        return QgsApplication.authManager().removeAuthenticationConfig(
            auth_config_id
        )

    def __old_connection_names(self) -> List[str]:
        old_settings = QSettings("NextGIS", "NextGIS WEB API")
        old_settings.beginGroup("/connections")
        old_connection_names = old_settings.childGroups()
        old_settings.endGroup()
        return old_connection_names

    def __save_auth_method(
        self,
        connection_name: str,
        resource: str,
        username: str,
        password: str,
    ) -> Optional[str]:
        if len(username) == 0 or len(password) == 0:
            return None

        config_name = f"{connection_name} / {username}"
        auth_manager = QgsApplication.authManager()

        configs = auth_manager.availableAuthMethodConfigs()
        for config_id, config in configs.items():
            if config.method() == "Basic" and config.name() == config_name:
                self.ensure_auth_resource(config_id, resource)
                return config_id

        auth_config = QgsAuthMethodConfig()
        auth_config.setName(config_name)
        auth_config.setMethod("Basic")
        auth_config.setUri(resource)
        auth_config.setConfig("username", username)
        auth_config.setConfig("password", password)

        auth_manager.storeAuthenticationConfig(auth_config, overwrite=True)

        return auth_config.id()
