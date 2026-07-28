from nextgis_connect.legacy.tree_widget.model import NgwSearch


def test_type_query_accepts_unquoted_value() -> None:
    search = NgwSearch("@type = vector_layer", set())

    queries = search._NgwSearch__queries()

    assert queries == ["cls=vector_layer"]


def test_type_query_keeps_quoted_value_support() -> None:
    search = NgwSearch('@type = "raster_layer"', set())

    queries = search._NgwSearch__queries()

    assert queries == ["cls=raster_layer"]


def test_owner_query_accepts_unquoted_display_name() -> None:
    search = NgwSearch("@owner = Alice Smith", set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}

    queries = search._NgwSearch__queries()

    assert queries == ["owner=1"]


def test_owner_query_keeps_quoted_display_name_support() -> None:
    search = NgwSearch('@owner = "Alice Smith"', set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}

    queries = search._NgwSearch__queries()

    assert queries == ["owner=1"]
