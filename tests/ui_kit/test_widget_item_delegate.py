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
