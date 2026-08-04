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

from typing import Dict, List

from qgis.core import QgsEditorWidgetSetup, QgsVectorLayer

from nextgis_connect.legacy.detached_editing.utils import is_ngw_container
from nextgis_connect.legacy.ngw.core.ngw_abstract_vector_resource import (
    NGWAbstractVectorResource,
)
from nextgis_connect.legacy.ngw.resources.ngw_data_type import NgwDataType
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModel


class QgisVectorLayerMetadataApplicator:
    """Apply NGW field and form metadata to one QGIS vector layer."""

    def __init__(self, resource_model: QNGWResourceTreeModel) -> None:
        self._resource_model = resource_model

    def apply(
        self,
        resource: NGWAbstractVectorResource,
        layer: QgsVectorLayer,
    ) -> None:
        """Apply aliases, widgets, constraints, and display expression."""
        self._apply_aliases(resource, layer)
        self._apply_edit_widgets(resource, layer)
        resource.fields.apply_required_constraints(layer)
        self._apply_display_field(resource, layer)

    @staticmethod
    def _apply_aliases(
        resource: NGWAbstractVectorResource,
        layer: QgsVectorLayer,
    ) -> None:
        qgis_fields = layer.fields()
        for ngw_field in resource.fields:
            if ngw_field.display_name is None:
                continue

            layer.setFieldAlias(
                qgis_fields.indexFromName(ngw_field.keyname),
                ngw_field.display_name,
            )

    def _apply_edit_widgets(
        self,
        resource: NGWAbstractVectorResource,
        layer: QgsVectorLayer,
    ) -> None:
        qgis_fields = layer.fields()
        lookup_tables: Dict[int, List[Dict[str, str]]] = {}

        if is_ngw_container(layer):
            primary_key_attributes = layer.primaryKeyAttributes()
            if len(primary_key_attributes) > 0:
                layer.setEditorWidgetSetup(
                    primary_key_attributes[0],
                    QgsEditorWidgetSetup("", {}),
                )

        for ngw_field in resource.fields:
            field_index = qgis_fields.indexFromName(ngw_field.keyname)
            if ngw_field.datatype == NgwDataType.TIME:
                layer.setEditorWidgetSetup(
                    field_index,
                    QgsEditorWidgetSetup(
                        "DateTime",
                        {
                            "display_format": "HH:mm:ss",
                            "field_format": "HH:mm:ss",
                            "field_format_overwrite": True,
                            "field_iso_format": False,
                            "allow_null": True,
                        },
                    ),
                )
                continue

            if ngw_field.datatype == NgwDataType.JSON:
                layer.setEditorWidgetSetup(
                    field_index,
                    QgsEditorWidgetSetup("JsonView", {}),
                )
                continue

            if ngw_field.lookup_table is None:
                continue

            lookup_table_id = ngw_field.lookup_table
            if lookup_table_id not in lookup_tables:
                lookup_table = self._resource_model.resource(lookup_table_id)
                lookup_tables[lookup_table_id] = [
                    {description: value}
                    for value, description in lookup_table._json[
                        "lookup_table"
                    ]["items"].items()
                ]

            layer.setEditorWidgetSetup(
                field_index,
                QgsEditorWidgetSetup(
                    "ValueMap",
                    {"map": lookup_tables[lookup_table_id]},
                ),
            )

    @staticmethod
    def _apply_display_field(
        resource: NGWAbstractVectorResource,
        layer: QgsVectorLayer,
    ) -> None:
        for field in resource.fields:
            if not field.is_label:
                continue

            layer.setDisplayExpression(f'"{field.keyname}"')
            return
