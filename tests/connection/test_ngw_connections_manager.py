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

import unittest
import uuid
from dataclasses import replace

from qgis.core import QgsApplication, QgsAuthMethodConfig
from qgis.PyQt.QtCore import QSettings

from nextgis_connect.legacy.ngw_connection import (
    ConnectionUpdateState,
    NgwConnection,
    NgwConnectionSettingsMigrator,
    NgwConnectionsManager,
)
from tests.ng_connect_testcase import NgConnectTestCase, TestConnection


class TestNgwConnectionsManager(NgConnectTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.connection(TestConnection.SandboxGuest)
        self.manager = NgwConnectionsManager()
        self.original_connections = self.manager.connections
        self.original_current_connection_id = (
            self.manager.current_connection_id
        )

    def tearDown(self) -> None:
        self.manager.replace_connections(self.original_connections)
        self.manager.current_connection_id = (
            self.original_current_connection_id
        )
        self.manager.save()
        super().tearDown()

    def test_connection_returns_none_for_missing_id(self) -> None:
        self.assertIsNone(self.manager.connection("missing-connection-id"))

    def test_find_connection_by_url_uses_normalized_url(self) -> None:
        connection = self.connection(TestConnection.SandboxGuest)

        duplicate = self.manager.find_connection_by_url(
            "http://sandbox.nextgis.com/resource/123/"
        )

        self.assertEqual(duplicate, connection)

    def test_find_connection_by_url_skips_excluded_connection(self) -> None:
        connection = replace(
            self.connection(TestConnection.SandboxGuest),
            id="excluded-connection-id",
            url="https://excluded.nextgis.com/",
        )
        self.manager.upsert(connection)
        self.manager.save()

        duplicate = self.manager.find_connection_by_url(
            connection.url,
            exclude_connection_id=connection.id,
        )

        self.assertIsNone(duplicate)

    def test_replace_connections_removes_missing_connections(self) -> None:
        guest_connection = self.connection(TestConnection.SandboxGuest)
        updated_guest_connection = replace(
            guest_connection,
            name="UPDATED_TEST_GUEST_CONNECTION",
        )
        login_connection_id = self.connection_id(
            TestConnection.SandboxWithLogin
        )

        self.manager.replace_connections([updated_guest_connection])

        self.assertEqual(
            self.manager.connection(updated_guest_connection.id),
            updated_guest_connection,
        )
        self.assertIsNone(self.manager.connection(login_connection_id))

    def test_save_emits_connection_updated_for_new_connection(
        self,
    ) -> None:
        guest_connection = self.connection(TestConnection.SandboxGuest)
        connection = replace(
            guest_connection,
            id="new-connection-id",
            url="https://new-sandbox.nextgis.com/",
        )
        updates = []
        self.manager.connection_updated.connect(
            lambda connection_id, state: updates.append((connection_id, state))
        )

        self.manager.upsert(connection)
        self.manager.save()

        self.assertEqual(
            updates,
            [(connection.id, ConnectionUpdateState.CREATED)],
        )

    def test_replace_connections_emits_connection_updated_for_changes(
        self,
    ) -> None:
        guest_connection = self.connection(TestConnection.SandboxGuest)
        login_connection = self.connection(TestConnection.SandboxWithLogin)
        demo_connection = self.connection(TestConnection.DemoGuest)
        connection = replace(
            guest_connection,
            url="https://changed-sandbox.nextgis.com/",
        )
        updates = []
        self.manager.connection_updated.connect(
            lambda connection_id, state: updates.append((connection_id, state))
        )

        self.manager.replace_connections(
            [
                connection,
                login_connection,
                demo_connection,
            ]
        )
        self.manager.save()

        self.assertEqual(
            updates,
            [(connection.id, ConnectionUpdateState.MODIFIED)],
        )

    def test_reset_discards_unsaved_changes(self) -> None:
        guest_connection = self.connection(TestConnection.SandboxGuest)
        updated_connection = replace(
            guest_connection,
            url="https://temporary-sandbox.nextgis.com/",
        )

        self.manager.upsert(updated_connection)

        self.assertTrue(self.manager.is_changed)

        self.manager.reset()

        self.assertFalse(self.manager.is_changed)
        self.assertEqual(
            self.manager.connection(guest_connection.id),
            guest_connection,
        )

    def test_auth_config_ids_for_connection_uses_resource_auths(self) -> None:
        connection = self.connection(TestConnection.SandboxWithLogin)
        extra_auth_config_id = self.__create_basic_auth_config(connection.url)

        self.assertEqual(
            self.manager.auth_config_ids_for_connection(connection.id),
            sorted([connection.auth_config_id, extra_auth_config_id]),
        )

    def test_auth_config_ids_for_guest_connection_ignores_guest(self) -> None:
        connection = replace(
            self.connection(TestConnection.SandboxGuest),
            id="guest-only-connection-id",
            url="https://guest-only.nextgis.com/",
        )
        self.manager.upsert(connection)

        self.assertEqual(
            self.manager.auth_config_ids_for_connection(connection.id),
            [],
        )

    def test_persisted_connection_auth_config_id_survives_reset(self) -> None:
        connection = self.connection(TestConnection.SandboxWithLogin)

        self.manager.set_connection_auth_config_id(
            connection.id,
            None,
            persist=True,
        )

        self.manager.reset()

        updated_connection = self.manager.connection(connection.id)
        self.assertIsNotNone(updated_connection)
        assert updated_connection is not None
        self.assertIsNone(updated_connection.auth_config_id)

    def test_migration_merges_duplicate_urls_and_keeps_current_connection(
        self,
    ) -> None:
        auth_config_id = self.__create_basic_auth_config()
        inactive_connection = NgwConnection(
            str(uuid.uuid4()),
            "Inactive duplicate",
            "http://duplicate.nextgis.com/resource/1",
            auth_config_id,
        )
        active_connection = NgwConnection(
            str(uuid.uuid4()),
            "Active duplicate",
            "https://duplicate.nextgis.com/",
            None,
        )

        connections, current_connection_id, changed = (
            NgwConnectionSettingsMigrator().merge_duplicate_web_gis_connections(
                [inactive_connection, active_connection],
                active_connection.id,
            )
        )

        self.assertTrue(changed)
        self.assertEqual(connections, [active_connection])
        self.assertEqual(current_connection_id, active_connection.id)
        self.assertEqual(
            self.__auth_config_resource(auth_config_id),
            "https://duplicate.nextgis.com",
        )

    def test_migration_does_not_change_current_connection_from_other_group(
        self,
    ) -> None:
        current_connection = NgwConnection(
            str(uuid.uuid4()),
            "Current",
            "https://current.nextgis.com/",
            None,
        )
        duplicate_connection_a = NgwConnection(
            str(uuid.uuid4()),
            "Duplicate A",
            "https://duplicate-a.nextgis.com/",
            None,
        )
        duplicate_connection_b = NgwConnection(
            str(uuid.uuid4()),
            "Duplicate B",
            "http://duplicate-a.nextgis.com/",
            None,
        )

        _, current_connection_id, changed = (
            NgwConnectionSettingsMigrator().merge_duplicate_web_gis_connections(
                [
                    current_connection,
                    duplicate_connection_a,
                    duplicate_connection_b,
                ],
                current_connection.id,
            )
        )

        self.assertTrue(changed)
        self.assertEqual(current_connection_id, current_connection.id)

    def test_migration_moves_connection_id_to_domain_uuid_and_keeps_old_id(
        self,
    ) -> None:
        connection = NgwConnection(
            "old-random-id",
            "Migrated",
            "https://migrated.nextgis.com/",
            None,
        )

        connections, current_connection_id, changed = (
            NgwConnectionSettingsMigrator().migrate_connection_ids_to_instance_ids(
                [connection],
                connection.id,
            )
        )

        self.assertTrue(changed)
        self.assertEqual(
            connections[0].id,
            NgwConnection.domain_uuid_for_url(connection.url),
        )
        self.assertEqual(connections[0].old_connection_ids, (connection.id,))
        self.assertEqual(current_connection_id, connections[0].id)

    def test_migration_keeps_random_connection_id_when_domain_uuid_exists(
        self,
    ) -> None:
        url = "https://collision.nextgis.com/"
        domain_connection = NgwConnection(
            NgwConnection.domain_uuid_for_url(url),
            "Domain",
            url,
            None,
        )
        random_connection = NgwConnection(
            "random-id",
            "Random",
            url,
            None,
        )

        connections, current_connection_id, changed = (
            NgwConnectionSettingsMigrator().migrate_connection_ids_to_instance_ids(
                [domain_connection, random_connection],
                random_connection.id,
            )
        )

        self.assertFalse(changed)
        self.assertEqual(connections, [domain_connection, random_connection])
        self.assertEqual(current_connection_id, random_connection.id)

    def test_manager_finds_connection_by_old_connection_id(self) -> None:
        connection = NgwConnection(
            "current-id",
            "Current",
            "https://current.nextgis.com/",
            None,
            ("old-id",),
        )
        manager = NgwConnectionsManager(
            connections=[connection],
            current_connection_id=connection.id,
        )

        self.assertEqual(manager.connection("old-id"), connection)

    def test_manager_normalizes_current_old_connection_id(self) -> None:
        connection = NgwConnection(
            "current-id",
            "Current",
            "https://current.nextgis.com/",
            None,
            ("old-id",),
        )
        manager = NgwConnectionsManager(
            connections=[connection],
            current_connection_id="old-id",
        )

        self.assertEqual(manager.current_connection_id, connection.id)
        self.assertEqual(manager.current_connection, connection)

    def test_migration_uses_domain_uuid_as_converted_connection_id(
        self,
    ) -> None:
        old_settings = QSettings("NextGIS", "NextGIS WEB API")
        old_settings.clear()
        url = "https://legacy-domain.nextgis.com/resource/1"
        old_settings.setValue("/connections/Legacy/server_url", url)
        old_settings.setValue("/connections/Legacy/username", "")
        old_settings.setValue("/connections/Legacy/password", "")
        old_settings.setValue("/connections/Legacy/oauth", False)

        try:
            connections, current_connection_id, changed = (
                NgwConnectionSettingsMigrator().convert_old_connections(
                    [],
                    None,
                    convert_auth=False,
                )
            )
        finally:
            old_settings.clear()

        self.assertTrue(changed)
        self.assertEqual(len(connections), 1)
        self.assertEqual(
            connections[0].id,
            NgwConnection.domain_uuid_for_url(url),
        )
        self.assertEqual(connections[0].old_connection_ids, ("Legacy",))
        self.assertIsNone(current_connection_id)

    def test_migration_generates_random_id_when_domain_uuid_exists(
        self,
    ) -> None:
        old_settings = QSettings("NextGIS", "NextGIS WEB API")
        old_settings.clear()
        url = "https://legacy-collision.nextgis.com/"
        existing_connection = NgwConnection(
            NgwConnection.domain_uuid_for_url(url),
            "Existing",
            "https://another.nextgis.com/",
            None,
        )
        old_settings.setValue("/connections/Legacy/server_url", url)
        old_settings.setValue("/connections/Legacy/username", "")
        old_settings.setValue("/connections/Legacy/password", "")
        old_settings.setValue("/connections/Legacy/oauth", False)

        try:
            connections, _, changed = (
                NgwConnectionSettingsMigrator().convert_old_connections(
                    [existing_connection],
                    None,
                    convert_auth=False,
                )
            )
        finally:
            old_settings.clear()

        self.assertTrue(changed)
        self.assertEqual(len(connections), 2)
        converted_connection = connections[1]
        self.assertNotEqual(converted_connection.id, existing_connection.id)
        uuid.UUID(converted_connection.id)

    def __create_basic_auth_config(self, resource: str = "") -> str:
        auth_config = QgsAuthMethodConfig("Basic")
        auth_config.setName(f"test_auth_config_{uuid.uuid4()}")
        auth_config.setUri(resource)
        auth_config.setConfig("username", "administrator")
        auth_config.setConfig("password", "demodemo")
        assert QgsApplication.authManager().storeAuthenticationConfig(
            auth_config
        )[0]
        return auth_config.id()

    def __auth_config_resource(self, auth_config_id: str) -> str:
        method_config = QgsAuthMethodConfig()
        assert QgsApplication.authManager().loadAuthenticationConfig(
            auth_config_id,
            method_config,
            True,
        )
        return method_config.uri()


if __name__ == "__main__":
    unittest.main()
