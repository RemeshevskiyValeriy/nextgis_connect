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

from unittest.mock import MagicMock, patch

from qgis.core import QgsVectorLayer

from nextgis_connect.legacy.detached_editing.container.container import (
    DetachedContainer,
)
from nextgis_connect.legacy.detached_editing.sync.common import (
    FetchAdditionalDataTask,
)
from nextgis_connect.legacy.detached_editing.sync.versioned import (
    FetchDeltaTask,
)
from nextgis_connect.platform.qgis.errors import (
    ContainerError,
    ErrorCode,
    NgwError,
)
from tests.detached_editing.utils import mock_container, set_container_version
from tests.ng_connect_testcase import NgConnectTestCase, TestData


class TestDetachedEditingTask(NgConnectTestCase):
    @mock_container(TestData.Points)
    def test_outdated_container_is_rejected_before_synchronization(
        self, container_mock: MagicMock, qgs_layer: QgsVectorLayer
    ) -> None:
        set_container_version(container_mock.path, "0.1.0")

        task = FetchAdditionalDataTask(
            container_mock.path, need_update_structure=True
        )

        assert task.error is not None
        assert task.error.code == ErrorCode.ContainerVersionIsOutdated
        assert task.run() is False

    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_versioning_epoch_mismatch_is_treated_as_epoch_changed(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer

        ngw_error = NgwError(
            "NGW communication error",
            user_message="Epoch mismatch.",
            ngw_exception_class=(
                "nextgisweb.feature_layer.versioning.exception."
                "FVersioningEpochMismatch"
            ),
        )
        module = (
            "nextgis_connect.legacy.detached_editing.sync.versioned."
            "fetch_delta_task"
        )
        with patch(f"{module}.QgsNgwConnection") as connection_mock:
            connection_mock.return_value.get.side_effect = ngw_error

            task = FetchDeltaTask(container_mock.path)

            assert task.run() is False

        assert task.error is not None
        assert task.error.code == ErrorCode.EpochChanged

    @mock_container(TestData.Points)
    def test_additional_data_network_error_preserves_network_context(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer

        network_error = NgwError(
            "Connection error",
            is_network_problem=True,
        )
        module = (
            "nextgis_connect.legacy.detached_editing.sync.common."
            "fetch_additional_data_task"
        )
        with patch(f"{module}.QgsNgwConnection") as connection_mock:
            connection_mock.return_value.get.side_effect = network_error
            task = FetchAdditionalDataTask(container_mock.path)

            assert task.run() is False

        assert task.error is not None
        assert task.error.is_network_problem
        assert "network problem" in task.error.user_message.lower()
        assert container_mock.metadata.layer_name in task.error.user_message
        assert (
            str(container_mock.metadata.resource_id)
            not in task.error.user_message
        )
        assert "fetching extra data" not in task.error.user_message.lower()

        error_notes = getattr(task.error, "__notes__", ())
        diagnostic_information = "\n".join(error_notes) + str(task.error)
        assert (
            str(container_mock.metadata.resource_id) in diagnostic_information
        )
        assert (
            f"Container path: {container_mock.path}" in diagnostic_information
        )

    @mock_container(TestData.Points)
    def test_additional_data_error_has_human_readable_message(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer

        module = (
            "nextgis_connect.legacy.detached_editing.sync.common."
            "fetch_additional_data_task"
        )
        with patch(f"{module}.QgsNgwConnection") as connection_mock:
            connection_mock.return_value.get.side_effect = ValueError(
                "Malformed response"
            )
            task = FetchAdditionalDataTask(container_mock.path)

            assert task.run() is False

        assert task.error is not None
        assert task.error.user_message == (
            f'Could not synchronize layer "{container_mock.metadata.layer_name}".'
        )
        assert (
            str(container_mock.metadata.resource_id)
            not in task.error.user_message
        )

    @mock_container(TestData.Points)
    def test_additional_data_server_error_has_contact_action(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer

        server_error = NgwError.from_json(
            {
                "status_code": 500,
                "title": "Internal server error",
                "message": "Internal server error",
                "detail": "Database connection pool is exhausted",
            }
        )
        module = (
            "nextgis_connect.legacy.detached_editing.sync.common."
            "fetch_additional_data_task"
        )
        with patch(f"{module}.QgsNgwConnection") as connection_mock:
            connection_mock.return_value.get.side_effect = server_error
            task = FetchAdditionalDataTask(container_mock.path)

            assert task.run() is False

        assert task.error is not None
        assert task.error.is_server_unavailable
        assert task.error.status_code == 500
        assert task.error.detail is None
        assert "temporarily unavailable" in task.error.user_message
        assert "try again later" in task.error.user_message.lower()
        assert container_mock.metadata.layer_name in task.error.user_message
        assert (
            str(container_mock.metadata.resource_id)
            not in task.error.user_message
        )
        assert [name for name, _callback in task.error.actions] == [
            "Contact us"
        ]

    @mock_container(TestData.Points)
    def test_container_error_diagnostics_include_container_path(
        self,
        container_mock: MagicMock,
        qgs_layer: QgsVectorLayer,
    ) -> None:
        del qgs_layer

        container = DetachedContainer(container_mock.path)
        self.addCleanup(container.deleteLater)

        error = ContainerError("Local container failure")
        process_error = container._DetachedContainer__process_error
        process_error(error, show_error=False)

        error_notes = getattr(error, "__notes__", ())
        diagnostic_information = "\n".join(error_notes) + str(error)
        assert (
            f"Container path: {container_mock.path}" in diagnostic_information
        )
