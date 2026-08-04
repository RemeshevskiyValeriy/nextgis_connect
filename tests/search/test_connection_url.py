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

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.legacy.search.connection_url import (
    SearchConnectionTargetResolver,
)


def test_resolver_ignores_plain_search_text() -> None:
    resolver = SearchConnectionTargetResolver()

    target = resolver.resolve(
        "roads",
        None,
        [],
    )

    assert target is None


def test_resolver_ignores_current_web_gis_url() -> None:
    current_connection = NgwConnection(
        "current",
        "Current",
        "https://demo.nextgis.com",
        None,
    )
    resolver = SearchConnectionTargetResolver()

    target = resolver.resolve(
        "https://demo.nextgis.com/resource/1",
        current_connection,
        [current_connection],
    )

    assert target is None


def test_resolver_returns_existing_connection_for_other_web_gis() -> None:
    current_connection = NgwConnection(
        "current",
        "Current",
        "https://current.nextgis.com",
        None,
    )
    target_connection = NgwConnection(
        "target",
        "Target",
        "https://target.nextgis.com",
        None,
    )
    resolver = SearchConnectionTargetResolver()

    target = resolver.resolve(
        "target.nextgis.com/resource/1",
        current_connection,
        [current_connection, target_connection],
    )

    assert target is not None
    assert target.url == "https://target.nextgis.com"
    assert target.connection == target_connection


def test_resolver_returns_missing_connection_target() -> None:
    current_connection = NgwConnection(
        "current",
        "Current",
        "https://current.nextgis.com",
        None,
    )
    resolver = SearchConnectionTargetResolver()

    target = resolver.resolve(
        "https://new.nextgis.com",
        current_connection,
        [current_connection],
    )

    assert target is not None
    assert target.url == "https://new.nextgis.com"
    assert target.connection is None


def test_resolver_accepts_bare_url_with_port() -> None:
    resolver = SearchConnectionTargetResolver()

    target = resolver.resolve(
        "localhost:8080",
        None,
        [],
    )

    assert target is not None
    assert target.url == "https://localhost:8080"
    assert target.connection is None
