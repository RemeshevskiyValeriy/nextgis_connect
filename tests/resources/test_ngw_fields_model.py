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

from unittest.mock import patch

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

from nextgis_connect.legacy.ngw.resources.ngw_data_type import NgwDataType
from nextgis_connect.legacy.ngw.resources.ngw_fields_model import (
    NgwFieldsModel,
)
from tests.ng_connect_testcase import NgConnectTestCase


class TestNgwFieldsModel(NgConnectTestCase):
    @patch(
        "nextgis_connect.legacy.ngw.resources.ngw_fields_model.material_icon",
        return_value=QIcon(),
    )
    def test_create_field_stores_required_flag(self, _material_icon) -> None:
        model = NgwFieldsModel()

        model.create_field(
            display_name="Name",
            keyname="name",
            datatype=NgwDataType.STRING,
            is_label=False,
            is_required=True,
            is_visible=True,
            is_used_for_search=True,
        )

        self.assertEqual(model.rowCount(), 1)
        self.assertTrue(model.fields[0].is_required)
        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.IS_REQUIRED,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Required</b><br/>The attribute must have a value.",
        )

    @patch(
        "nextgis_connect.legacy.ngw.resources.ngw_fields_model.material_icon",
        return_value=QIcon(),
    )
    def test_field_attribute_headers_have_tooltips(
        self, _material_icon
    ) -> None:
        model = NgwFieldsModel()

        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.DISPLAY_NAME,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Display name</b><br/>Display name that is used in the "
            "identification window instead of the keyname.",
        )
        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.KEYNAME,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Keyname</b><br/>Technical name of the attribute, can be "
            "comprised only of plain latin symbols.",
        )
        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.DATATYPE,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Type</b><br/>Attribute value type.",
        )
        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.IS_VISIBLE,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Feature table</b><br/>The attribute is displayed in the "
            "identification window.",
        )
        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.IS_USED_FOR_SEARCH,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Text search</b><br/>You can disable text search in the values of the "
            "attribute.",
        )
        self.assertEqual(
            model.headerData(
                NgwFieldsModel.Column.IS_LABEL,
                Qt.Orientation.Horizontal,
                Qt.ItemDataRole.ToolTipRole,
            ),
            "<b>Label attribute</b><br/>Value from this field is used as feature name "
            "for search results, identification and bookmarks.",
        )

    @patch(
        "nextgis_connect.legacy.ngw.resources.ngw_fields_model.material_icon",
        return_value=QIcon(),
    )
    def test_set_data_updates_required_flag(self, _material_icon) -> None:
        model = NgwFieldsModel()
        model.create_field(
            display_name="Name",
            keyname="name",
            datatype=NgwDataType.STRING,
            is_label=False,
            is_required=False,
            is_visible=True,
            is_used_for_search=True,
        )

        index = model.index(0, NgwFieldsModel.Column.IS_REQUIRED)

        self.assertTrue(model.setData(index, True))
        self.assertTrue(model.fields[0].is_required)
