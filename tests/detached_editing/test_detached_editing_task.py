from unittest.mock import MagicMock, patch

from qgis.core import QgsVectorLayer

from nextgis_connect.legacy.detached_editing.sync.common import (
    FetchAdditionalDataTask,
)
from nextgis_connect.legacy.detached_editing.sync.versioned import (
    FetchDeltaTask,
)
from nextgis_connect.platform.qgis.errors import ErrorCode, NgwError
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
