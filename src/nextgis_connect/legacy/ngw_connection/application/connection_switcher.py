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

from dataclasses import replace
from typing import Optional

from nextgis_connect.legacy.ngw_connection.application.connections_manager import (
    NgwConnectionsManager,
)


class NgwConnectionSwitcher:
    def __init__(self, connections_manager: NgwConnectionsManager) -> None:
        self.__connections_manager = connections_manager

    def switch(
        self,
        connection_id: str,
        auth_config_id: Optional[str],
    ) -> bool:
        connection = self.__connections_manager.connection(connection_id)
        if connection is None:
            return False

        if (
            self.__connections_manager.current_connection_id == connection_id
            and connection.auth_config_id == auth_config_id
        ):
            return False

        updated_connection = replace(
            connection,
            auth_config_id=auth_config_id,
        )
        self.__connections_manager.upsert(updated_connection)
        self.__connections_manager.current_connection_id = connection_id
        self.__connections_manager.save()
        return True
