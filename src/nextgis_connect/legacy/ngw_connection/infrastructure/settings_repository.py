# NextGIS Connect
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

import json
from dataclasses import dataclass
from typing import List, Optional, Tuple

from qgis.core import QgsSettings

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)


@dataclass(frozen=True)
class ConnectionSettingsSnapshot:
    connections: Tuple[NgwConnection, ...]
    current_connection_id: Optional[str]


class QgisConnectionSettingsRepository:
    CONNECTIONS_KEY = "/NextGIS/Connect/connections"
    CURRENT_CONNECTION_KEY = "NextGIS/Connect/currentConnectionId"

    def __init__(self, settings: Optional[QgsSettings] = None) -> None:
        self.__settings = QgsSettings() if settings is None else settings

    def read_snapshot(self) -> ConnectionSettingsSnapshot:
        return ConnectionSettingsSnapshot(
            connections=tuple(self.__read_connections()),
            current_connection_id=self.read_current_connection_id(),
        )

    def read_current_connection_id(self) -> Optional[str]:
        return self.__settings.value(
            self.CURRENT_CONNECTION_KEY,
            defaultValue=None,
        )

    def write_snapshot(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
    ) -> None:
        self.__settings.remove(self.CONNECTIONS_KEY)
        for connection in connections:
            self.write_connection(connection)

        self.__settings.setValue(
            self.CURRENT_CONNECTION_KEY,
            current_connection_id,
        )

    def write_connection(self, connection: NgwConnection) -> None:
        connection_key = f"{self.CONNECTIONS_KEY}/{connection.id}"
        self.__settings.setValue(f"{connection_key}/name", connection.name)
        self.__settings.setValue(f"{connection_key}/url", connection.url)
        self.__settings.setValue(
            f"{connection_key}/auth_config",
            connection.auth_config_id,
        )
        self.__settings.setValue(
            f"{connection_key}/old_connection_ids",
            json.dumps(list(connection.old_connection_ids)),
        )

    def __read_connections(self) -> List[NgwConnection]:
        self.__settings.beginGroup(self.CONNECTIONS_KEY)
        connection_ids = self.__settings.childGroups()
        self.__settings.endGroup()
        return [
            self.__read_connection(connection_id)
            for connection_id in connection_ids
        ]

    def __read_connection(self, connection_id: str) -> NgwConnection:
        connection_key = f"{self.CONNECTIONS_KEY}/{connection_id}"
        name = self.__settings.value(
            f"{connection_key}/name",
            "",
            type=str,
        )
        url = self.__settings.value(
            f"{connection_key}/url",
            "",
            type=str,
        )
        auth_config_id = self.__settings.value(f"{connection_key}/auth_config")
        if auth_config_id == "":
            auth_config_id = None
        return NgwConnection(
            connection_id,
            name,
            url,
            auth_config_id,
            self.__read_old_connection_ids(connection_key),
        )

    def __read_old_connection_ids(
        self,
        connection_key: str,
    ) -> Tuple[str, ...]:
        value = self.__settings.value(
            f"{connection_key}/old_connection_ids",
            "[]",
            type=str,
        )
        try:
            old_connection_ids = json.loads(value)
        except (TypeError, ValueError):
            return ()

        if not isinstance(old_connection_ids, list):
            return ()

        return tuple(
            old_connection_id
            for old_connection_id in old_connection_ids
            if isinstance(old_connection_id, str)
            and len(old_connection_id) > 0
        )
