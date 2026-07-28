from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.legacy.search.resource_url import SearchResourceUrlParser


def test_parser_reads_resource_url() -> None:
    connection = NgwConnection(
        "connection",
        "Connection",
        "https://demo.nextgis.com",
        None,
    )

    resource_id = SearchResourceUrlParser().resource_id(
        "https://demo.nextgis.com/resource/42",
        connection,
    )

    assert resource_id == "42"


def test_parser_reads_api_resource_url() -> None:
    connection = NgwConnection(
        "connection",
        "Connection",
        "https://demo.nextgis.com",
        None,
    )

    resource_id = SearchResourceUrlParser().resource_id(
        "https://demo.nextgis.com/api/resource/42",
        connection,
    )

    assert resource_id == "42"


def test_parser_reads_api_resource_url_with_trailing_parts() -> None:
    connection = NgwConnection(
        "connection",
        "Connection",
        "https://demo.nextgis.com",
        None,
    )

    resource_id = SearchResourceUrlParser().resource_id(
        "https://demo.nextgis.com/api/resource/42/feature/?limit=10",
        connection,
    )

    assert resource_id == "42"


def test_parser_ignores_other_web_gis_url() -> None:
    connection = NgwConnection(
        "connection",
        "Connection",
        "https://demo.nextgis.com",
        None,
    )

    resource_id = SearchResourceUrlParser().resource_id(
        "https://other.nextgis.com/api/resource/42",
        connection,
    )

    assert resource_id is None


def test_parser_ignores_non_resource_url() -> None:
    connection = NgwConnection(
        "connection",
        "Connection",
        "https://demo.nextgis.com",
        None,
    )

    resource_id = SearchResourceUrlParser().resource_id(
        "https://demo.nextgis.com/resource/create",
        connection,
    )

    assert resource_id is None
