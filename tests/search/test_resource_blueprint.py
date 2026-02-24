from nextgis_connect.features.search.domain.resource_blueprint import (
    ResourceBlueprintLabelParser,
    ResourceBlueprintTypeParser,
)


def test_parser_reads_resource_cls_enum_values() -> None:
    parser = ResourceBlueprintTypeParser()

    resource_types = parser.parse(
        {
            "resource": {
                "cls": {
                    "enum": [
                        "resource_group",
                        ["vector_layer", "Vector layer"],
                        {"identity": "raster_layer", "label": "Raster"},
                    ]
                }
            }
        }
    )

    assert resource_types == [
        "raster_layer",
        "resource_group",
        "vector_layer",
    ]


def test_parser_reads_resource_type_tree_items() -> None:
    parser = ResourceBlueprintTypeParser()

    resource_types = parser.parse(
        {
            "children": [
                {"id": "webmap", "display_name": "Web map"},
                {"value": "baselayers", "label": "Basemaps"},
            ]
        }
    )

    assert resource_types == ["baselayers", "webmap"]


def test_parser_reads_type_like_mapping_keys() -> None:
    parser = ResourceBlueprintTypeParser()

    resource_types = parser.parse(
        {
            "resource_group": {"label": "Group"},
            "vector_layer": {"label": "Vector layer"},
        }
    )

    assert resource_types == ["resource_group", "vector_layer"]


def test_parser_ignores_resource_field_names() -> None:
    parser = ResourceBlueprintTypeParser()

    resource_types = parser.parse(
        {
            "resource": {
                "display_name": {"type": "string"},
                "parent": {"type": "integer"},
            }
        }
    )

    assert resource_types == []


def test_label_parser_reads_resource_cls_enum_labels() -> None:
    parser = ResourceBlueprintLabelParser()

    resource_labels = parser.parse(
        {
            "resource": {
                "cls": {
                    "enum": [
                        ["vector_layer", "Vector layer"],
                        {
                            "identity": "raster_layer",
                            "label": "Raster layer",
                        },
                    ]
                }
            }
        }
    )

    assert resource_labels == {
        "raster_layer": "Raster layer",
        "vector_layer": "Vector layer",
    }


def test_label_parser_reads_type_like_mapping_labels() -> None:
    parser = ResourceBlueprintLabelParser()

    resource_labels = parser.parse(
        {
            "resource_group": {"label": "Resource group"},
            "vector_layer": {"display_name": "Vector layer"},
        }
    )

    assert resource_labels == {
        "resource_group": "Resource group",
        "vector_layer": "Vector layer",
    }
