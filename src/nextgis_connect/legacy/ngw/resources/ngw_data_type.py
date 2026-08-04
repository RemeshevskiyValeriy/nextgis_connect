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

from enum import IntEnum
from typing import cast

from qgis.PyQt.QtGui import QIcon

from nextgis_connect.platform.qgis.compat import FieldType
from nextgis_connect.ui_kit.icons import field_type_icon


class NgwDataType(IntEnum):
    INTEGER = cast(int, FieldType.Int)
    BIGINT = cast(int, FieldType.LongLong)
    REAL = cast(int, FieldType.Double)
    STRING = cast(int, FieldType.QString)
    JSON = cast(int, FieldType.QVariantMap)
    TIME = cast(int, FieldType.QTime)
    DATE = cast(int, FieldType.QDate)
    DATETIME = cast(int, FieldType.QDateTime)
    BOOLEAN = cast(int, FieldType.Bool)

    @property
    def icon(self) -> QIcon:
        return field_type_icon(self.qt_value)

    @property
    def qt_value(self):
        return FieldType(self.value)

    @staticmethod
    def from_name(type_name: str):
        try:
            return NgwDataType[type_name]
        except KeyError:
            return NgwDataType.STRING

    @staticmethod
    def from_qt_value(qt_value: FieldType):
        if qt_value in (
            FieldType.QVariantMap,
            FieldType.QJsonValue,
            FieldType.QJsonObject,
            FieldType.QJsonArray,
        ):
            return NgwDataType.JSON

        return NgwDataType(cast(int, qt_value))
