import pytest

from nextgis_connect.legacy.ngw.core.ngw_resource import NGWResource
from nextgis_connect.legacy.tree_widget.model import NgwSearch
from nextgis_connect.platform.qgis.errors import NgConnectError


class ResourceFactoryStub:
    connection = object()

    def __init__(self) -> None:
        self.requested_json = []

    def get_resource_by_json(self, resource_json):
        self.requested_json.append(resource_json)
        return ResourceStub(
            resource_id=resource_json["resource"]["id"],
            parent_id=resource_json["resource"]["parent"]["id"],
            grandparent_id=resource_json["resource"]["parent"]["parent"]["id"],
        )


class ResourceStub:
    def __init__(
        self,
        resource_id: int,
        parent_id: int,
        grandparent_id,
    ) -> None:
        self.resource_id = resource_id
        self.parent_id = parent_id
        self.grandparent_id = grandparent_id


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


def test_owner_query_accepts_current_user_alias() -> None:
    search = NgwSearch("@owner = me", set())
    search.current_user_id = 7

    queries = search._NgwSearch__queries()

    assert queries == ["owner=7"]


def test_owner_in_query_accepts_current_user_alias() -> None:
    search = NgwSearch('@owner IN ("me", "Alice Smith")', set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}
    search.current_user_id = 7

    queries = search._NgwSearch__queries()

    assert queries == ["owner__in=1,7"]


def test_owner_ilike_query_accepts_current_user_alias() -> None:
    search = NgwSearch("@owner ILIKE me", set())
    search.current_user_id = 7

    queries = search._NgwSearch__queries()

    assert queries == ["owner=7"]


def test_owner_like_query_accepts_current_user_alias() -> None:
    search = NgwSearch('@owner LIKE "me"', set())
    search.current_user_id = 7

    queries = search._NgwSearch__queries()

    assert queries == ["owner=7"]


def test_owner_like_query_matches_users_case_sensitively() -> None:
    search = NgwSearch('@owner LIKE "Alice%"', set())
    search.users_keyname = {"alice": 1}
    search.users_username = {"Alice Smith": 1}

    queries = search._NgwSearch__queries()

    assert queries == ["owner=1"]


def test_name_query_supports_like_operator() -> None:
    search = NgwSearch('@name LIKE "Roads"', set())

    queries = search._NgwSearch__queries()

    assert queries == ["display_name__like=Roads"]


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


def test_owner_like_query_raises_when_user_is_missing() -> None:
    search = NgwSearch('@owner LIKE "Missing%"', set())
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


def test_fetch_children_stops_on_root_parent(monkeypatch) -> None:
    requested_parent_ids = []

    def receive_resource_children(connection, parent_id, *, feedback=None):
        del connection, feedback
        requested_parent_ids.append(parent_id)
        if parent_id == 12:
            return [
                {
                    "resource": {
                        "id": 34,
                        "parent": {
                            "id": 12,
                            "parent": {"id": None},
                        },
                    },
                }
            ]

        raise AssertionError(f"Unexpected parent id: {parent_id}")

    monkeypatch.setattr(
        NGWResource,
        "receive_resource_children",
        receive_resource_children,
    )

    search = NgwSearch("Roads", set())
    resources_factory = ResourceFactoryStub()

    search._NgwSearch__fetch_children(resources_factory, 12)

    assert requested_parent_ids == [12]
    assert search.result.added_resources[0].resource_id == 34
