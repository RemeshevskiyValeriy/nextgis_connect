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

from nextgis_connect.features.search.domain.resource_owners import (
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


def test_parser_ignores_system_users() -> None:
    parser = ResourceOwnerSuggestionParser()

    owner_names = parser.parse(
        [
            {
                "id": 1,
                "keyname": "system",
                "display_name": "System",
                "system": True,
            },
            {
                "id": 2,
                "keyname": "alice",
                "display_name": "Alice Smith",
                "system": False,
            },
        ]
    )

    assert owner_names == ["Alice Smith"]
