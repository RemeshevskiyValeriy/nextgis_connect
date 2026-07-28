from dataclasses import dataclass
from typing import List, Optional, Tuple

import pytest

from nextgis_connect.legacy.ngw_connection.application.connections_manager import (
    ConnectionUpdateState,
    NgwConnectionsManager,
)
from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.legacy.ngw_connection.infrastructure.settings_repository import (
    ConnectionSettingsSnapshot,
)
from tests.ng_connect_testcase import start_qgis


@dataclass
class SavedSnapshot:
    connections: Tuple[NgwConnection, ...]
    current_connection_id: Optional[str]


class InMemoryConnectionSettingsRepository:
    def __init__(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
    ) -> None:
        self._snapshot = ConnectionSettingsSnapshot(
            tuple(connections),
            current_connection_id,
        )
        self.saved_snapshot: Optional[SavedSnapshot] = None
        self.written_connections: List[NgwConnection] = []

    def read_snapshot(self) -> ConnectionSettingsSnapshot:
        return self._snapshot

    def read_current_connection_id(self) -> Optional[str]:
        return self._snapshot.current_connection_id

    def write_snapshot(
        self,
        connections: List[NgwConnection],
        current_connection_id: Optional[str],
    ) -> None:
        self.saved_snapshot = SavedSnapshot(
            tuple(connections),
            current_connection_id,
        )

    def write_connection(self, connection: NgwConnection) -> None:
        self.written_connections.append(connection)


@pytest.fixture()
def qgis_app() -> None:
    start_qgis()


def test_manager_persists_snapshot_through_repository(qgis_app) -> None:
    del qgis_app
    first_connection = NgwConnection(
        "first-id",
        "First",
        "https://first.nextgis.com",
        None,
    )
    second_connection = NgwConnection(
        "second-id",
        "Second",
        "https://second.nextgis.com",
        None,
    )
    repository = InMemoryConnectionSettingsRepository(
        [first_connection],
        first_connection.id,
    )
    manager = NgwConnectionsManager(
        connections=[first_connection],
        current_connection_id=first_connection.id,
        settings_repository=repository,
    )
    emitted_updates = []
    manager.connection_updated.connect(
        lambda connection_id, state: emitted_updates.append(
            (connection_id, state)
        )
    )

    manager.upsert(second_connection)
    manager.current_connection_id = second_connection.id
    manager.save()

    assert repository.saved_snapshot == SavedSnapshot(
        (first_connection, second_connection),
        second_connection.id,
    )
    assert emitted_updates == [
        (second_connection.id, ConnectionUpdateState.CREATED)
    ]


def test_manager_normalizes_missing_current_connection(qgis_app) -> None:
    del qgis_app
    alpha_connection = NgwConnection(
        "alpha-id",
        "Alpha",
        "https://alpha.nextgis.com",
        None,
    )
    beta_connection = NgwConnection(
        "beta-id",
        "Beta",
        "https://beta.nextgis.com",
        None,
    )

    manager = NgwConnectionsManager(
        connections=[beta_connection, alpha_connection],
        current_connection_id="missing-id",
        settings_repository=InMemoryConnectionSettingsRepository([], None),
    )

    assert manager.current_connection_id == alpha_connection.id
    assert manager.current_connection == alpha_connection
