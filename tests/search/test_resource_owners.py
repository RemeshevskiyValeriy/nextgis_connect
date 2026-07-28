from nextgis_connect.legacy.search.resource_owners import (
    ResourceOwnerSuggestionParser,
)


def test_parser_reads_user_display_names() -> None:
    parser = ResourceOwnerSuggestionParser()

    owner_names = parser.parse(
        [
            {
                "id": 1,
                "keyname": "alice",
                "display_name": "Alice Smith",
            },
            {
                "id": 2,
                "keyname": "bob",
                "display_name": "Bob",
            },
        ]
    )

    assert owner_names == ["Alice Smith", "Bob"]


def test_parser_falls_back_to_keyname() -> None:
    parser = ResourceOwnerSuggestionParser()

    owner_names = parser.parse(
        [
            {
                "id": 1,
                "keyname": "alice",
                "display_name": "",
            },
        ]
    )

    assert owner_names == ["alice"]


def test_parser_ignores_invalid_users() -> None:
    parser = ResourceOwnerSuggestionParser()

    owner_names = parser.parse(
        [
            {"id": 1},
            "alice",
            {
                "id": 2,
                "keyname": "bob",
                "display_name": "Bob",
            },
        ]
    )

    assert owner_names == ["Bob"]
