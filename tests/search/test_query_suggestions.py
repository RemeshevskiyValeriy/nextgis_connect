from nextgis_connect.legacy.search.query_suggestions import (
    TextSearchSuggestionBuilder,
)


def test_keyword_suggestions_are_available_after_at_sign() -> None:
    suggestions = TextSearchSuggestionBuilder().keyword_suggestions("@")

    assert suggestions == [
        "@id",
        "@parent",
        "@root",
        "@owner",
        "@type",
        "@name",
        "@keyname",
        "@metadata",
    ]


def test_keyword_suggestions_filter_by_prefix() -> None:
    suggestions = TextSearchSuggestionBuilder().keyword_suggestions("@t")

    assert suggestions == ["@type"]


def test_keyword_suggestions_preserve_previous_query_text() -> None:
    suggestions = TextSearchSuggestionBuilder().keyword_suggestions(
        "@owner = 1 AND @n"
    )

    assert suggestions == ["@owner = 1 AND @name"]


def test_resource_type_suggestions_are_available_after_type_equals() -> None:
    suggestions = TextSearchSuggestionBuilder().resource_type_suggestions(
        "@type = ",
        ["raster_layer", "vector_layer", "webmap"],
    )

    assert suggestions == [
        "@type = raster_layer",
        "@type = vector_layer",
        "@type = webmap",
    ]


def test_resource_type_suggestions_filter_value_prefix() -> None:
    suggestions = TextSearchSuggestionBuilder().resource_type_suggestions(
        "@type=vec",
        ["raster_layer", "vector_layer", "webmap"],
    )

    assert suggestions == ["@type=vector_layer"]


def test_resource_type_suggestions_preserve_opening_quote() -> None:
    suggestions = TextSearchSuggestionBuilder().resource_type_suggestions(
        '@type = "r',
        ["raster_layer", "vector_layer"],
    )

    assert suggestions == ['@type = "raster_layer"']


def test_owner_suggestions_are_available_after_owner_equals() -> None:
    suggestions = TextSearchSuggestionBuilder().owner_suggestions(
        "@owner = ",
        ["Alice Smith", "Bob"],
    )

    assert suggestions == ["@owner = Alice Smith", "@owner = Bob"]


def test_owner_suggestions_filter_value_prefix() -> None:
    suggestions = TextSearchSuggestionBuilder().owner_suggestions(
        "@owner=ali",
        ["Alice Smith", "Bob"],
    )

    assert suggestions == ["@owner=Alice Smith"]


def test_owner_suggestions_preserve_opening_quote() -> None:
    suggestions = TextSearchSuggestionBuilder().owner_suggestions(
        '@owner = "ali',
        ["Alice Smith", "Bob"],
    )

    assert suggestions == ['@owner = "Alice Smith"']


def test_owner_suggestions_skip_values_incompatible_with_quote() -> None:
    suggestions = TextSearchSuggestionBuilder().owner_suggestions(
        '@owner = "',
        ['Alice "QA"', "Bob"],
    )

    assert suggestions == ['@owner = "Bob"']
