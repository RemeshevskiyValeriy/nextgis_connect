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
