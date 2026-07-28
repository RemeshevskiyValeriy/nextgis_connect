from unittest.mock import MagicMock

from qgis.core import QgsVectorLayer

from nextgis_connect.legacy.detached_editing.sync.common import (
    FetchAdditionalDataTask,
)
from nextgis_connect.platform.qgis.errors import ErrorCode
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
