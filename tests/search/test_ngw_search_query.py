from nextgis_connect.legacy.tree_widget.model import NgwSearch


def test_type_query_accepts_unquoted_value() -> None:
    search = NgwSearch("@type = vector_layer", set())

    queries = search._NgwSearch__queries()

    assert queries == ["cls=vector_layer"]


def test_type_query_keeps_quoted_value_support() -> None:
    search = NgwSearch('@type = "raster_layer"', set())

    queries = search._NgwSearch__queries()

    assert queries == ["cls=raster_layer"]
