import pytest

from nextgis_connect.legacy.tree_widget.model import NgwSearch
from nextgis_connect.platform.qgis.errors import NgConnectError


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


def test_owner_query_raises_when_user_is_missing() -> None:
    search = NgwSearch("@owner = Missing User", set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}

    with pytest.raises(NgConnectError, match="User not found: Missing User"):
        search._NgwSearch__queries()


def test_owner_query_raises_when_quoted_user_is_missing() -> None:
    search = NgwSearch('@owner = "Missing User"', set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}

    with pytest.raises(NgConnectError, match="User not found: Missing User"):
        search._NgwSearch__queries()


def test_owner_ilike_query_raises_when_user_is_missing() -> None:
    search = NgwSearch('@owner ILIKE "Missing%"', set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}

    with pytest.raises(NgConnectError, match="User not found: Missing%"):
        search._NgwSearch__queries()


def test_search_job_can_be_canceled() -> None:
    search = NgwSearch("Roads", set())

    search.cancel()

    assert search._feedback is not None
    assert search._feedback.isCanceled()


def test_canceled_search_raises_cancel_error() -> None:
    search = NgwSearch("Roads", set())
    search.cancel()

    with pytest.raises(NgConnectError):
        search._NgwSearch__raise_if_canceled()
