from typing import List

from qgis.PyQt import sip
from qgis.PyQt.QtCore import QModelIndex, QPersistentModelIndex
from qgis.PyQt.QtWidgets import (
    QListView,
    QStyleOptionViewItem,
    QWidget,
)

from nextgis_connect.ui_kit.delegates.widget_item_delegate import (
    WidgetItemDelegate,
)


class _ProbeWidgetItemDelegate(WidgetItemDelegate):
    def _create_item_widgets(self, index: QModelIndex) -> List[QWidget]:
        del index
        return [QWidget()]

    def _update_item_widgets(
        self,
        widgets: List[QWidget],
        option: QStyleOptionViewItem,
        index: QPersistentModelIndex,
    ) -> None:
        del widgets
        del option
        del index


def test_widget_item_delegate_ignores_initialization_after_view_deleted(
    qgis_app,
) -> None:
    view = QListView()
    delegate = _ProbeWidgetItemDelegate(view)

    try:
        sip.delete(view)

        delegate._initialize_model()
        qgis_app.processEvents()

        assert not delegate._has_valid_item_view()
    finally:
        if not sip.isdeleted(delegate):
            sip.delete(delegate)
