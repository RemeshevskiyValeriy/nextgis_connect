from nextgis_connect.legacy.search.search_settings import SearchSettings
from nextgis_connect.legacy.search.text_search_completer_model import (
    TextSearchCompleterModel,
)


def test_history_suggestions_hide_unmatched_text_prefix(
    qgis_app,
    reset_qgis_settings,
) -> None:
    del qgis_app, reset_qgis_settings

    settings = SearchSettings()
    settings.add_text_query_to_history("@owner = me")

    model = TextSearchCompleterModel(None)
    model.set_prefix("vector")

    assert not model.stringList()


def test_history_suggestions_filter_by_text_prefix(
    qgis_app,
    reset_qgis_settings,
) -> None:
    del qgis_app, reset_qgis_settings

    settings = SearchSettings()
    settings.add_text_query_to_history("@owner = me")
    settings.add_text_query_to_history("Vector roads")

    model = TextSearchCompleterModel(None)
    model.set_prefix("vector")

    assert model.stringList() == ["Vector roads"]
