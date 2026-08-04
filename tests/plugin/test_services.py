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

from unittest.mock import Mock, patch

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.plugin.services import initialize_connections


def test_initialize_connections_reassigns_cache_after_migration() -> None:
    connection = NgwConnection(
        "connection-id",
        "Connection",
        "https://example.nextgis.com",
        None,
    )
    connections_manager = Mock()
    connections_manager.is_migrated = True
    connections_manager.connections = [connection]

    with patch(
        "nextgis_connect.plugin.services.NgwConnectionsManager",
        return_value=connections_manager,
    ):
        with patch(
            "nextgis_connect.plugin.services.CacheMaintenanceService"
        ) as cache_service_class:
            initialize_connections()

    cache_service = cache_service_class.return_value
    cache_service.reassign_container_connection_ids.assert_called_once_with(
        [connection]
    )
    connections_manager.clear_old_connections_if_converted.assert_called_once_with()


def test_initialize_connections_skips_cache_without_migration() -> None:
    connections_manager = Mock()
    connections_manager.is_migrated = False
    connections_manager.connections = []

    with patch(
        "nextgis_connect.plugin.services.NgwConnectionsManager",
        return_value=connections_manager,
    ):
        with patch(
            "nextgis_connect.plugin.services.CacheMaintenanceService"
        ) as cache_service_class:
            initialize_connections()

    cache_service_class.assert_not_called()
    connections_manager.clear_old_connections_if_converted.assert_called_once_with()
