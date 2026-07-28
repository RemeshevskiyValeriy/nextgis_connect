from dataclasses import dataclass
from typing import Any, Dict, Optional, Union

from qgis.core import QgsField, QgsFieldConstraints, QgsVectorLayer

from nextgis_connect.legacy.ngw.resources.ngw_data_type import NgwDataType
from nextgis_connect.platform.qgis.compat import FieldType
from nextgis_connect.shared.types import FieldId


@dataclass(frozen=True, init=False)
class NgwField:
    """NextGIS Web vector layer field metadata.

    :ivar datatype: Attribute value type.
    :ivar keyname: Technical name of the attribute, can be comprised only of
        plain latin symbols.
    :ivar display_name: Display name that is used in the identification window
        instead of the keyname.
    :ivar is_label: Value from this field is used as feature name for search
        results, identification and bookmarks.
    :ivar is_required: The attribute must have a value.
    :ivar is_visible: The attribute is displayed in the identification window.
    :ivar is_used_for_search: Text search is enabled in the values of the
        attribute.
    """

    ngw_id: FieldId
    datatype: NgwDataType
    keyname: str
    display_name: str
    is_label: bool
    is_required: bool
    is_visible: bool
    is_used_for_search: bool
    lookup_table: Optional[int] = None
    attribute: int

    def __init__(
        self,
        ngw_id: FieldId,
        datatype: Union[str, FieldType, NgwDataType],
        keyname: str,
        display_name: str,
        is_label: bool,
        is_required: bool = False,
        is_visible: bool = True,
        is_used_for_search: bool = True,
        lookup_table: Optional[int] = None,
        attribute: int = -1,
    ) -> None:
        super().__setattr__("ngw_id", ngw_id)
        if isinstance(datatype, str):
            super().__setattr__("datatype", NgwDataType.from_name(datatype))
        elif isinstance(datatype, FieldType):
            super().__setattr__(
                "datatype", NgwDataType.from_qt_value(datatype)
            )
        elif isinstance(datatype, NgwDataType):
            super().__setattr__("datatype", datatype)
        super().__setattr__("keyname", keyname)
        super().__setattr__("display_name", display_name)
        super().__setattr__("is_label", is_label)
        super().__setattr__("is_required", is_required)
        super().__setattr__("is_visible", is_visible)
        super().__setattr__("is_used_for_search", is_used_for_search)
        super().__setattr__("lookup_table", lookup_table)
        super().__setattr__("attribute", attribute)

    def is_compatible(
        self,
        rhs: Union["NgwField", QgsField],
        *,
        layer: Optional[QgsVectorLayer] = None,
        compare_required: bool = True,
    ) -> bool:
        if isinstance(rhs, NgwField):
            is_required_compatible = (
                not compare_required or self.is_required == rhs.is_required
            )
            return (
                self.ngw_id == rhs.ngw_id
                and self.datatype == rhs.datatype
                and self.keyname == rhs.keyname
                and is_required_compatible
            )
        else:
            datatype = self.datatype.qt_value

            if datatype == FieldType.QTime:
                # GPKG does not have Time type
                datatype = FieldType.QString

            if self.datatype == NgwDataType.JSON:
                is_same_datatype = self.is_qgs_field_json(rhs)
            else:
                is_same_datatype = datatype == rhs.type()

            is_required_compatible = (
                not compare_required
                or self.is_required
                == self.is_qgs_field_required(rhs, layer=layer)
            )

            return (
                is_same_datatype
                and self.keyname == rhs.name()
                and is_required_compatible
            )

    def to_qgs_field(self) -> QgsField:
        field = QgsField(self.keyname, self.datatype.qt_value)
        if self.is_required:
            constraints = field.constraints()
            constraints.setConstraint(
                QgsFieldConstraints.Constraint.ConstraintNotNull
            )
            field.setConstraints(constraints)

        return field

    @staticmethod
    def is_qgs_field_required(
        field: QgsField, *, layer: Optional[QgsVectorLayer] = None
    ) -> bool:
        constraints = field.constraints().constraints()
        if layer is not None:
            field_index = layer.fields().indexFromName(field.name())
            if field_index != -1:
                constraints |= layer.fieldConstraints(field_index)

        return bool(
            constraints & QgsFieldConstraints.Constraint.ConstraintNotNull
        )

    @staticmethod
    def is_qgs_field_json(field: QgsField) -> bool:
        type_name = field.typeName().lower()
        return (
            field.type()
            in (
                FieldType.QVariantMap,
                FieldType.QJsonValue,
                FieldType.QJsonObject,
                FieldType.QJsonArray,
            )
            or "map" in type_name
            or "json" in type_name
        )

    def to_json(self) -> Dict[str, Any]:
        result = {
            "datatype": self.datatype.name,
            "keyname": self.keyname,
            "display_name": self.display_name,
            "label_field": self.is_label,
            "required": self.is_required,
            "grid_visibility": self.is_visible,
            "text_search": self.is_used_for_search,
            "lookup_table": {"id": self.lookup_table}
            if self.lookup_table
            else None,
        }
        if self.ngw_id != -1:
            result["id"] = self.ngw_id

        return result

    @staticmethod
    def from_json(json: Dict[str, Any], *, index: int = -1) -> "NgwField":
        def get_lookup_table(field: Dict[str, Any]) -> Optional[int]:
            table = field.get("lookup_table")
            if table is None:
                return None
            return table.get("id")

        return NgwField(
            attribute=index,
            ngw_id=json["id"],
            datatype=json["datatype"],
            keyname=json["keyname"],
            display_name=json.get("display_name", json["id"]),
            is_label=json.get("label_field", False),
            is_required=json.get("required", False),
            is_visible=json.get("grid_visibility", True),
            is_used_for_search=json.get("text_search", True),
            lookup_table=get_lookup_table(json),
        )

    def __repr__(self) -> str:
        class_name = self.__class__.__name__
        return f"<{class_name}: {self.keyname} ({self.ngw_id})>"
