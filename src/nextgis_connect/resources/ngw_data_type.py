from enum import IntEnum
from typing import cast

from qgis.core import QgsFields
from qgis.PyQt.QtGui import QIcon

from nextgis_connect.compat import FieldType


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
        return QgsFields.iconForFieldType(self.qt_value)

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
