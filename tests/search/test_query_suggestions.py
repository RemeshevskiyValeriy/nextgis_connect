from nextgis_connect.features.search.domain.query_suggestions import (
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


def test_operation_suggestions_are_available_after_string_tag() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions("@name")

    assert suggestions == [
        '@name = "',
        '@name LIKE "',
        '@name ILIKE "',
        '@name IN ("',
    ]


def test_operation_suggestions_are_available_after_numeric_tag() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions("@id")

    assert suggestions == ["@id = ", "@id IN ("]


def test_operation_suggestions_skip_unsupported_in_operation() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions("@root")

    assert suggestions == ["@root = "]


def test_operation_suggestions_for_owner_use_unquoted_values() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions("@owner")

    assert suggestions == [
        "@owner = ",
        "@owner LIKE ",
        "@owner ILIKE ",
        '@owner IN ("',
    ]


def test_operation_suggestions_filter_by_operation_prefix() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions(
        "@name i"
    )

    assert suggestions == ['@name ILIKE "', '@name IN ("']


def test_operation_suggestions_preserve_previous_query_text() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions(
        "@owner = me AND @id i"
    )

    assert suggestions == ["@owner = me AND @id IN ("]


def test_operation_suggestions_ignore_metadata_tag() -> None:
    suggestions = TextSearchSuggestionBuilder().operation_suggestions(
        "@metadata"
    )

    assert suggestions is None


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

    assert suggestions == [
        "@owner = me",
        "@owner = Alice Smith",
        "@owner = Bob",
    ]


def test_owner_suggestions_filter_value_prefix() -> None:
    suggestions = TextSearchSuggestionBuilder().owner_suggestions(
        "@owner=ali",
        ["Alice Smith", "Bob"],
    )

    assert suggestions == ["@owner = Alice Smith"]


def test_owner_suggestions_include_current_user_alias() -> None:
    suggestions = TextSearchSuggestionBuilder().owner_suggestions(
        "@owner = m",
        ["Alice Smith", "Bob"],
    )

    assert suggestions == ["@owner = me"]


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

    assert suggestions == ['@owner = "me"', '@owner = "Bob"']
