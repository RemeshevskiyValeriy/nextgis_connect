import json

from nextgis_connect.legacy.detached_editing.sync.common.changes import (
    AttachmentSource,
    AttachmentUpdate,
)
from nextgis_connect.legacy.detached_editing.sync.versioned.actions import (
    ActionType,
)
from nextgis_connect.legacy.detached_editing.sync.versioned.versioned_changes_serializer import (
    VersionedChangesSerializer,
)
from tests.detached_editing.utils import mock_container
from tests.ng_connect_testcase import (
    NgConnectTestCase,
    TestData,
)


class TestVersionedChangesSerializer(NgConnectTestCase):
    @mock_container(TestData.Points, is_versioning_enabled=True)
    def test_to_json_serializes_attachment_source_dataclass(
        self, container_mock, _qgs_layer
    ) -> None:
        serializer = VersionedChangesSerializer(container_mock.metadata)
        change = AttachmentUpdate(
            fid=1,
            ngw_fid=101,
            aid=10,
            ngw_aid=501,
            version=7,
            source=AttachmentSource(
                source_type="file_upload",
                data={
                    "id": "uploaded-file-id",
                    "size": 128,
                },
            ),
            name="photo.jpg",
            description="Attachment description",
            keyname="photo",
            mime_type="image/jpeg",
        )

        payload = serializer.to_json([change])

        self.assertEqual(
            json.loads(payload),
            [
                [
                    0,
                    {
                        "action": str(ActionType.ATTACHMENT_UPDATE),
                        "fid": 101,
                        "aid": 501,
                        "vid": 7,
                        "source": {
                            "type": "file_upload",
                            "id": "uploaded-file-id",
                            "size": 128,
                        },
                        "name": "photo.jpg",
                        "description": "Attachment description",
                        "keyname": "photo",
                        "mime_type": "image/jpeg",
                    },
                ]
            ],
        )
