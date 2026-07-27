import unittest
from dataclasses import FrozenInstanceError

from qgis.core import QgsField, QgsFieldConstraints

from nextgis_connect.compat import FieldType
from nextgis_connect.resources.ngw_field import NgwField
from nextgis_connect.resources.ngw_fields import NgwFields
from tests.ng_connect_testcase import NgConnectTestCase


class TestNgwField(NgConnectTestCase):
    def setUp(self):
        self.field_json = {
            "id": 1,
            "datatype": "STRING",
            "keyname": "name",
            "display_name": "Name",
            "label_field": True,
            "required": True,
            "lookup_table": {"id": 10},
        }

    def test_datatypes_serializing(self):
        field_types = {
            "INTEGER": FieldType.Int,
            "BIGINT": FieldType.LongLong,
            "REAL": FieldType.Double,
            "STRING": FieldType.QString,
            "JSON": FieldType.QVariantMap,
            "DATE": FieldType.QDate,
            "TIME": FieldType.QTime,
            "DATETIME": FieldType.QDateTime,
            "BOOLEAN": FieldType.Bool,
            # ---
            "UNKNOWN": FieldType.QString,
        }
        for datatype_name, datatype in field_types.items():
            field = NgwField(
                attribute=0,
                ngw_id=1,
                datatype=datatype_name,
                keyname="name",
                display_name="Name",
                is_label=False,
            )
            self.assertEqual(field.datatype.qt_value, datatype)

    def test_is_compatible_with_ngwfield(self):
        field1 = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=False,
        )
        field2 = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=False,
        )
        self.assertTrue(field1.is_compatible(field2))

        field1 = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=False,
        )
        field2 = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="REAL",
            keyname="name",
            display_name="Name",
            is_label=False,
        )
        self.assertFalse(field1.is_compatible(field2))

    def test_is_compatible_with_qgsfield(self):
        field = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=True,
        )
        qgs_field = QgsField("name", FieldType.QString)
        self.assertTrue(field.is_compatible(qgs_field))

        field = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=True,
        )
        qgs_field = QgsField("name", FieldType.Int)
        self.assertFalse(field.is_compatible(qgs_field))

    def test_to_qgs_field(self):
        field = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=True,
        )
        qgs_field = field.to_qgs_field()
        self.assertEqual(qgs_field.name(), "name")
        self.assertEqual(qgs_field.type(), FieldType.QString)
        self.assertFalse(
            qgs_field.constraints().constraints()
            & QgsFieldConstraints.Constraint.ConstraintNotNull
        )

    def test_to_qgs_field_sets_not_null_for_required_field(self):
        field = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=True,
            is_required=True,
        )

        qgs_field = field.to_qgs_field()

        self.assertTrue(
            qgs_field.constraints().constraints()
            & QgsFieldConstraints.Constraint.ConstraintNotNull
        )

    def test_from_json(self):
        field = NgwField.from_json(self.field_json)
        self.assertEqual(field.ngw_id, 1)
        self.assertEqual(field.datatype.name, "STRING")
        self.assertEqual(field.keyname, "name")
        self.assertEqual(field.display_name, "Name")
        self.assertTrue(field.is_label)
        self.assertTrue(field.is_required)
        self.assertEqual(field.lookup_table, 10)

    def test_from_json_json_type_uses_qvariant_map(self):
        field = NgwField.from_json({**self.field_json, "datatype": "JSON"})

        self.assertEqual(field.datatype.qt_value, FieldType.QVariantMap)

    def test_from_qt_json_types_map_to_ngw_json(self):
        for qt_type in (
            FieldType.QVariantMap,
            FieldType.QJsonValue,
            FieldType.QJsonObject,
            FieldType.QJsonArray,
        ):
            with self.subTest(qt_type=qt_type):
                field = NgwField(
                    attribute=0,
                    ngw_id=1,
                    datatype=qt_type,
                    keyname="name",
                    display_name="Name",
                    is_label=False,
                )

                self.assertEqual(field.datatype.name, "JSON")

    def test_is_qgs_field_required(self):
        qgs_field = QgsField("name", FieldType.QString)
        constraints = qgs_field.constraints()
        constraints.setConstraint(
            QgsFieldConstraints.Constraint.ConstraintNotNull
        )
        qgs_field.setConstraints(constraints)

        self.assertTrue(NgwField.is_qgs_field_required(qgs_field))

    def test_frozen_class(self):
        field = NgwField(
            attribute=0,
            ngw_id=1,
            datatype="STRING",
            keyname="name",
            display_name="Name",
            is_label=True,
        )
        with self.assertRaises(FrozenInstanceError):
            field.ngw_id = 2  # type: ignore


class TestNgwFields(NgConnectTestCase):
    def setUp(self):
        self.field_json = {
            "id": 1,
            "datatype": "STRING",
            "keyname": "name",
            "display_name": "Name",
            "label_field": True,
            "lookup_table": {"id": 10},
        }

    def test_list_from_json(self):
        fields_data = [
            {**self.field_json, "id": 1, "keyname": "field_1"},
            {**self.field_json, "id": 2, "keyname": "field_2"},
        ]

        fields = NgwFields.from_json(fields_data)
        self.assertEqual(len(fields), 2)
        self.assertEqual(fields[0].attribute, 0)
        self.assertEqual(fields[0].keyname, "field_1")
        self.assertEqual(fields[1].attribute, 1)
        self.assertEqual(fields[1].keyname, "field_2")


if __name__ == "__main__":
    unittest.main()
