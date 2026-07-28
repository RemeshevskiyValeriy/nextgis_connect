from nextgis_connect.legacy.detached_editing.sync.versioned.actions import (
    AttachmentDeleteAction,
    ContinueAction,
    FeatureDeleteAction,
    FeatureUpdateAction,
)
from nextgis_connect.legacy.detached_editing.sync.versioned.actions_filter import (
    ActionsFilter,
)
from tests.ng_connect_testcase import NgConnectTestCase


class TestActionsFilter(NgConnectTestCase):
    FEATURE_VERSION = 11
    ATTACHMENT_VERSION = 21

    def test_filter_removes_continue_actions(self) -> None:
        actions = [
            FeatureUpdateAction(fid=101, vid=self.FEATURE_VERSION),
            ContinueAction(url="https://example.test/next"),
        ]

        result = ActionsFilter().filter(actions)

        self.assertEqual(
            result,
            [FeatureUpdateAction(fid=101, vid=self.FEATURE_VERSION)],
        )

    def test_filter_removes_attachment_delete_after_feature_delete(
        self,
    ) -> None:
        actions = [
            FeatureDeleteAction(fid=101, vid=self.FEATURE_VERSION),
            AttachmentDeleteAction(
                fid=101,
                aid=201,
                vid=self.ATTACHMENT_VERSION,
            ),
            AttachmentDeleteAction(
                fid=102,
                aid=202,
                vid=self.ATTACHMENT_VERSION,
            ),
        ]

        result = ActionsFilter().filter(actions)

        self.assertEqual(
            result,
            [
                FeatureDeleteAction(fid=101, vid=self.FEATURE_VERSION),
                AttachmentDeleteAction(
                    fid=102,
                    aid=202,
                    vid=self.ATTACHMENT_VERSION,
                ),
            ],
        )

    def test_filter_keeps_attachment_delete_before_feature_delete(
        self,
    ) -> None:
        actions = [
            AttachmentDeleteAction(
                fid=101,
                aid=201,
                vid=self.ATTACHMENT_VERSION,
            ),
            FeatureDeleteAction(fid=101, vid=self.FEATURE_VERSION),
        ]

        result = ActionsFilter().filter(actions)

        self.assertEqual(result, actions)

    def test_filter_resets_deleted_features_between_calls(self) -> None:
        filter_ = ActionsFilter()
        filter_.filter(
            [FeatureDeleteAction(fid=101, vid=self.FEATURE_VERSION)]
        )

        result = filter_.filter(
            [
                AttachmentDeleteAction(
                    fid=101,
                    aid=201,
                    vid=self.ATTACHMENT_VERSION,
                )
            ]
        )

        self.assertEqual(
            result,
            [
                AttachmentDeleteAction(
                    fid=101,
                    aid=201,
                    vid=self.ATTACHMENT_VERSION,
                )
            ],
        )
