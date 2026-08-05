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

from typing import cast

from qgis.gui import QgsTimeEdit
from qgis.PyQt.QtWidgets import QWidget

from nextgis_connect.legacy.detached_editing.conflicts.ui.feature_delete_conflict_tab import (
    FeatureDeleteConflictTab,
)


class TestFeatureDeleteConflictTab:
    def test_set_read_only_handles_time_edit_without_clear_button(
        self,
        qgis_app,
    ) -> None:
        del qgis_app

        parent = QWidget()
        edit_widget = QgsTimeEdit(parent)
        tab = cast(FeatureDeleteConflictTab, object())

        FeatureDeleteConflictTab._set_read_only(tab, edit_widget, True)

        assert edit_widget.isReadOnly()

        FeatureDeleteConflictTab._set_read_only(tab, edit_widget, False)

        assert not edit_widget.isReadOnly()

        parent.deleteLater()
