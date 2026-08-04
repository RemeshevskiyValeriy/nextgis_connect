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

import configparser
import os
import uuid
from dataclasses import replace
from pathlib import Path

import pytest
import qgis.utils
from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsVectorLayer, edit
from qgis.PyQt.QtCore import QObject

from nextgis_connect.legacy.detached_editing.container.container_factory import (
    DetachedContainerFactory,
)
from nextgis_connect.legacy.detached_editing.container.editing.container_sessions import (
    ContainerReadOnlySession,
)
from nextgis_connect.legacy.detached_editing.detached_layer import (
    DetachedLayer,
)
from nextgis_connect.legacy.detached_editing.sync.common.upload_changes_task import (
    UploadChangesTask,
)
from nextgis_connect.legacy.detached_editing.sync.versioned.fill_layer_with_versioning_task import (
    FillLayerWithVersioningTask,
)
from nextgis_connect.legacy.detached_editing.utils import (
    DetachedContainerContext,
    container_metadata,
    detached_layer_uri,
)
from nextgis_connect.legacy.ngw.core.ngw_feature import NGWFeature
from nextgis_connect.legacy.ngw.core.ngw_resource import NGWResource
from nextgis_connect.legacy.ngw.core.ngw_resource_creator import (
    ResourceCreator,
)
from nextgis_connect.legacy.ngw.core.ngw_resource_factory import (
    NGWResourceFactory,
)
from nextgis_connect.legacy.ngw.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    QgsNgwConnection,
)
from nextgis_connect.legacy.ngw_connection import NgwConnectionsManager
from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.shared.constants import PACKAGE_NAME
from tests.magic_qobject_mock import MagicQObjectMock
from tests.ng_connect_testcase import NgConnectTestCase, TestData


@pytest.mark.skipif(
    os.environ.get("NEXTGIS_CONNECT_RUN_NETWORK_TESTS") != "1",
    reason="requires live NextGIS sandbox access",
)
class TestSandboxVersionedSync(NgConnectTestCase):
    TEST_AUTH_ID = "ngtest-sandbox-live-basic"
    TEST_CONNECTION_ID = "ngtest-sandbox-live-basic-connection"

    def setUp(self) -> None:
        super().setUp()

        previous_plugin = qgis.utils.plugins.get(PACKAGE_NAME)
        previous_metadata = qgis.utils.plugins_metadata_parser.get(
            PACKAGE_NAME
        )
        self.addCleanup(
            self._restore_plugin_state,
            previous_plugin,
            previous_metadata,
        )

        plugin = QObject()
        metadata = configparser.ConfigParser()
        metadata.read(
            Path(__file__).resolve().parents[2]
            / "src/nextgis_connect/metadata.txt",
            encoding="utf-8",
        )
        plugin.metadata = metadata
        plugin.version = metadata.get("general", "version")
        plugin.path = (
            Path(__file__).resolve().parents[2] / "src/nextgis_connect"
        )
        qgis.utils.plugins[PACKAGE_NAME] = plugin
        qgis.utils.plugins_metadata_parser[PACKAGE_NAME] = metadata

    @staticmethod
    def _restore_plugin_state(
        previous_plugin: object,
        previous_metadata: object,
    ) -> None:
        if previous_plugin is None:
            qgis.utils.plugins.pop(PACKAGE_NAME, None)
        else:
            qgis.utils.plugins[PACKAGE_NAME] = previous_plugin

        if previous_metadata is None:
            qgis.utils.plugins_metadata_parser.pop(PACKAGE_NAME, None)
        else:
            qgis.utils.plugins_metadata_parser[PACKAGE_NAME] = (
                previous_metadata
            )

    def _sandbox_factory(self) -> NGWResourceFactory:
        auth_manager = QgsApplication.authManager()
        auth_config = QgsAuthMethodConfig("Basic")
        auth_config.setId(self.TEST_AUTH_ID)
        auth_config.setName(self.TEST_AUTH_ID)
        auth_config.setUri("https://sandbox.nextgis.com/")
        auth_config.setConfig("username", "administrator")
        auth_config.setConfig("password", "demodemo")
        assert auth_manager.storeAuthenticationConfig(
            auth_config,
            overwrite=True,
        )[0]
        self.addCleanup(
            auth_manager.removeAuthenticationConfig,
            auth_config.id(),
        )

        connection = NgwConnection(
            self.TEST_CONNECTION_ID,
            "sandbox-live-basic",
            "https://sandbox.nextgis.com/",
            auth_config.id(),
        )
        connections_manager = NgwConnectionsManager()
        connections_manager.upsert(connection)
        connections_manager.save()
        self.addCleanup(self._remove_test_connection, connection.id)
        return NGWResourceFactory(QgsNgwConnection(connection))

    @staticmethod
    def _remove_test_connection(connection_id: str) -> None:
        connections_manager = NgwConnectionsManager()
        connections_manager.remove(connection_id)
        connections_manager.save()

    def _create_sandbox_group(self) -> NGWResource:
        factory = self._sandbox_factory()
        root_resource = factory.get_root_resource()
        group_name = f"test-detached-sync-{uuid.uuid4().hex[:8]}"
        group_resource = ResourceCreator.create_group(
            root_resource, group_name
        )
        self.addCleanup(NGWResource.delete_resource, group_resource)
        return group_resource

    def _upload_versioned_vector_layer(self) -> NGWVectorLayer:
        group_resource = self._create_sandbox_group()
        layer_name = f"versioned-{uuid.uuid4().hex[:8]}"
        source_path = self.data_path(TestData.Points)

        vector_layer = ResourceCreator.create_vector_layer(
            group_resource,
            str(source_path),
            layer_name,
            "fid",
            lambda *_args: None,
            lambda: None,
        )
        vector_layer.set_versioning_enabled(True)
        vector_layer.update()

        self.assertTrue(vector_layer.is_versioning_enabled)
        return vector_layer

    def _create_filled_container(
        self,
        vector_layer: NGWVectorLayer,
    ) -> tuple[MagicQObjectMock, QgsVectorLayer]:
        container_path = self.create_temp_file(".gpkg")

        factory = DetachedContainerFactory()
        factory.create_initial_container(vector_layer, container_path)

        fill_task = FillLayerWithVersioningTask(container_path)
        self.assertTrue(fill_task.run(), fill_task.error)

        metadata = container_metadata(container_path)
        qgs_layer = QgsVectorLayer(
            detached_layer_uri(container_path, metadata),
            metadata.layer_name,
            "ogr",
        )
        self.assertTrue(qgs_layer.isValid())
        self.assertGreater(qgs_layer.featureCount(), 0)
        self.addCleanup(qgs_layer.deleteLater)

        container = MagicQObjectMock()
        container.path = container_path
        container.metadata = metadata
        container.context = DetachedContainerContext(container_path, metadata)
        return container, qgs_layer

    def _first_feature_ids(self, container_path: Path) -> tuple[int, int]:
        with ContainerReadOnlySession(container_path) as cursor:
            row = cursor.execute(
                """
                SELECT fid, ngw_fid
                FROM ngw_features_metadata
                ORDER BY fid
                LIMIT 1
                """
            ).fetchone()

        assert row is not None
        return row[0], row[1]

    def _remote_feature(
        self,
        layer: NGWVectorLayer,
        feature_id: int,
    ) -> NGWFeature:
        response = layer.res_factory.connection.get(
            f"{layer.get_feature_adding_url()}{feature_id}"
        )
        return NGWFeature(response, layer)

    def _fetch_all_actions(self, layer: NGWVectorLayer) -> list[dict]:
        connection = layer.res_factory.connection
        check_result = connection.get(
            f"/api/resource/{layer.resource_id}/feature/changes/check?extensions=attachment,description"
        )

        actions = []
        fetched_actions = connection.get(check_result["fetch"])
        while fetched_actions:
            actions.extend(fetched_actions)
            continue_action = fetched_actions[-1]
            if "url" not in continue_action:
                break
            fetched_actions = connection.get(continue_action["url"])

        return actions

    def test_upload_changes_task_updates_remote_description(self) -> None:
        vector_layer = self._upload_versioned_vector_layer()
        container, qgs_layer = self._create_filled_container(vector_layer)
        detached_layer = DetachedLayer(container, qgs_layer)

        local_fid, remote_fid = self._first_feature_ids(container.path)
        new_description = f"sandbox-description-{uuid.uuid4().hex[:8]}"

        with edit(qgs_layer):
            detached_layer.set_feature_description(local_fid, new_description)

        upload_task = UploadChangesTask(container.path)
        self.assertTrue(upload_task.run(), upload_task.error)

        descriptions = [
            action
            for action in self._fetch_all_actions(vector_layer)
            if action.get("action") == "description.put"
            and action.get("fid") == remote_fid
            and action.get("value") == new_description
        ]
        self.assertTrue(descriptions)

    def test_upload_changes_task_creates_remote_attachment(self) -> None:
        vector_layer = self._upload_versioned_vector_layer()
        container, qgs_layer = self._create_filled_container(vector_layer)
        detached_layer = DetachedLayer(container, qgs_layer)

        local_fid, remote_fid = self._first_feature_ids(container.path)
        attachment_path = self.create_temp_file(".txt")
        attachment_path.write_text(
            f"sandbox-attachment-{uuid.uuid4().hex}",
            encoding="utf-8",
        )
        attachment_description = (
            f"sandbox-attachment-description-{uuid.uuid4().hex[:8]}"
        )

        with edit(qgs_layer):
            attachment = detached_layer.add_attachment(
                local_fid, attachment_path
            )
            detached_layer.update_attachment(
                replace(
                    attachment,
                    description=attachment_description,
                )
            )

        upload_task = UploadChangesTask(container.path)
        self.assertTrue(upload_task.run(), upload_task.error)

        attachment_actions = [
            action
            for action in self._fetch_all_actions(vector_layer)
            if action.get("action") == "attachment.create"
            and action.get("fid") == remote_fid
            and action.get("name") == attachment_path.name
        ]
        self.assertTrue(attachment_actions)
        self.assertEqual(
            attachment_actions[-1].get("mime_type"),
            attachment.mime_type,
        )
        self.assertEqual(
            attachment_actions[-1].get("description"),
            attachment_description,
        )

        attachments = self._remote_feature(
            vector_layer, remote_fid
        ).get_attachments()
        matching_attachments = [
            attachment
            for attachment in attachments
            if attachment.get("name") == attachment_path.name
        ]
        self.assertTrue(matching_attachments)
        self.assertEqual(
            matching_attachments[-1].get("mime_type"),
            attachment.mime_type,
        )
        self.assertEqual(
            matching_attachments[-1].get("description"),
            attachment_description,
        )
