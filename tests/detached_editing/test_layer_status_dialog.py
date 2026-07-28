from pathlib import Path
from types import SimpleNamespace

from qgis import utils as qgis_utils
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QObject, pyqtSignal

from nextgis_connect.legacy.detached_editing.container.ui.layer_status_dialog import (
    DetachedLayerStatusDialog,
)
from nextgis_connect.legacy.detached_editing.utils import DetachedLayerState
from nextgis_connect.shared.constants import PACKAGE_NAME
from tests.ng_connect_testcase import NgConnectTestCase


class _Metadata:
    has_changes = False


class _ChangesInfo:
    added_features_count = 0
    removed_features_count = 0
    updated_features_count = 0


class _Container(QObject):
    editing_started = pyqtSignal()
    editing_finished = pyqtSignal()
    state_changed = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.state = DetachedLayerState.Synchronized
        self.metadata = _Metadata()
        self.is_edit_mode_enabled = False
        self.sync_date = None
        self.error = None
        self.changes_info = _ChangesInfo()

    def synchronize(self, is_manual: bool = False) -> None:
        del is_manual

    def reset_container(self) -> None:
        pass


class TestDetachedLayerStatusDialog(NgConnectTestCase):
    def test_sync_and_close_buttons_stay_in_same_row(self) -> None:
        old_plugin = qgis_utils.plugins.get(PACKAGE_NAME)
        qgis_utils.plugins[PACKAGE_NAME] = SimpleNamespace(
            path=Path(__file__).resolve().parents[2] / "src/nextgis_connect"
        )
        try:
            dialog = DetachedLayerStatusDialog(_Container())
            dialog.show()
            QgsApplication.instance().processEvents()

            self.assertEqual(
                dialog.syncButton.geometry().y(),
                dialog.closeButton.geometry().y(),
            )
            self.assertFalse(dialog.syncButton.defaultAction().icon().isNull())
            self.assertFalse(
                dialog.syncButton.menu().actions()[0].icon().isNull()
            )
        finally:
            if old_plugin is None:
                qgis_utils.plugins.pop(PACKAGE_NAME, None)
            else:
                qgis_utils.plugins[PACKAGE_NAME] = old_plugin

            if "dialog" in locals():
                dialog.close()
                dialog.deleteLater()
