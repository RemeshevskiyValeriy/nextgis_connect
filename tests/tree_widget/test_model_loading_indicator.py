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

from pathlib import Path
from types import SimpleNamespace

from qgis.PyQt.QtCore import QModelIndex, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QIcon, QPalette

from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.legacy.tree_widget.model import (
    QNGWResourceTreeModelBase,
    ResourceTreeLoadingIndicatorRenderer,
)
from nextgis_connect.legacy.tree_widget.proxy_model import NgConnectProxyModel
from nextgis_connect.legacy.tree_widget.view import QNGWResourceTreeView
from nextgis_connect.platform.qgis.errors import NgwError
from nextgis_connect.plugin.plugin_interface import NgConnectInterface
from nextgis_connect.ui_kit.graphics import (
    NextgisDecorator,
    mix_colors,
)


class _Job:
    def error(self):
        return None


class _FailedFetchJob:
    def __init__(self, error: NgwError) -> None:
        self._error = error

    def error(self) -> NgwError:
        return self._error

    def getJobId(self) -> str:
        return "NGWResourceUpdater"


def _resource(resource_id: int = 1):
    return SimpleNamespace(
        display_name="Resource",
        common=SimpleNamespace(cls="vector_layer"),
        icon_path="",
        resource_id=resource_id,
        type_id="vector_layer",
        connection=SimpleNamespace(server_url=""),
    )


def test_locked_resource_item_uses_loading_indicator_icon(qgis_app) -> None:
    del qgis_app

    model = QNGWResourceTreeModelBase()
    item = QNGWResourceItem(_resource())
    model.root_item.addChild(item)
    index = model.index(0, 0, QModelIndex())
    job = _Job()

    default_icon = model.data(index, Qt.ItemDataRole.DecorationRole)
    assert not default_icon.isNull()
    default_icon_cache_key = default_icon.cacheKey()

    model._lockIndexByJob([index], job)

    loading_icon = model.data(index, Qt.ItemDataRole.DecorationRole)
    assert not loading_icon.isNull()
    assert loading_icon.cacheKey() != default_icon_cache_key

    model._unlockIndexesByJob(job)

    restored_icon = model.data(index, Qt.ItemDataRole.DecorationRole)
    assert restored_icon.cacheKey() == default_icon_cache_key


def test_failed_group_fetch_can_be_retried(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    model = QNGWResourceTreeModelBase()
    item = QNGWResourceItem(_resource())
    model.root_item.addChild(item)
    index = model.index(0, 0, QModelIndex())
    error = NgwError("Connection error", is_network_problem=True)
    job = _FailedFetchJob(error)
    fetched_indexes = []

    model._lockIndexByJob([index], job)
    prepare_error = model._QNGWResourceTreeModelBase__add_fetch_retry_action
    prepare_error(job, error)
    model._unlockIndexesByJob(job)

    assert error.try_again is not None
    assert not model._isIndexLockedByJobError(index)

    monkeypatch.setattr(model, "canFetchMore", lambda parent: True)
    monkeypatch.setattr(model, "fetchMore", fetched_indexes.append)
    error.try_again()

    assert fetched_indexes == [index]
    assert not model._isIndexLockedByJobError(index)


def test_failed_group_fetch_is_unlocked_for_manual_expansion(
    qgis_app,
) -> None:
    del qgis_app

    model = QNGWResourceTreeModelBase()
    item = QNGWResourceItem(_resource())
    model.root_item.addChild(item)
    index = model.index(0, 0, QModelIndex())
    error = NgwError("Connection error", is_network_problem=True)
    job = _FailedFetchJob(error)

    model._lockIndexByJob([index], job)
    model._unlockIndexesByJob(job)
    assert not model._isIndexLockedByJobError(index)

    was_cleared = model.clear_fetch_error(index)

    assert not was_cleared
    assert not model._isIndexLockedByJobError(index)


def test_failed_group_fetch_collapses_expanded_item_for_retry(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app
    monkeypatch.setattr(
        NgConnectInterface,
        "instance",
        classmethod(
            lambda cls: SimpleNamespace(path=Path("src/nextgis_connect"))
        ),
    )

    model = QNGWResourceTreeModelBase()
    resource = _resource()
    resource.common.children = True
    resource.children_count = None
    item = QNGWResourceItem(resource)
    model.root_item.addChild(item)
    index = model.index(0, 0, QModelIndex())
    error = NgwError("Connection error", is_network_problem=True)
    job = _FailedFetchJob(error)

    proxy_model = NgConnectProxyModel(None)
    proxy_model.setSourceModel(model)
    view = QNGWResourceTreeView(None)
    view.setModel(proxy_model)
    view.expand(proxy_model.mapFromSource(index))

    assert view.isExpanded(proxy_model.mapFromSource(index))

    model._lockIndexByJob([index], job)
    model._unlockIndexesByJob(job)

    assert not view.isExpanded(proxy_model.mapFromSource(index))

    fetched_indexes = []
    monkeypatch.setattr(model, "canFetchMore", lambda parent: True)
    monkeypatch.setattr(model, "fetchMore", fetched_indexes.append)

    retry_failed_fetch = view._QNGWResourceTreeView__retry_failed_fetch
    retry_failed_fetch(proxy_model.mapFromSource(index))

    assert len(fetched_indexes) == 1
    assert fetched_indexes[0].internalPointer() is item

    view.deleteLater()
    proxy_model.deleteLater()


def test_resource_tree_loading_indicator_uses_readable_colors(
    qgis_app,
) -> None:
    del qgis_app

    text_color = QColor("#102030")
    base_color = QColor("#f0f0f0")
    highlighted_text_color = QColor("#ffffff")
    highlight_color = QColor("#2458c8")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Base, base_color)
    palette.setColor(
        QPalette.ColorRole.HighlightedText,
        highlighted_text_color,
    )
    palette.setColor(QPalette.ColorRole.Highlight, highlight_color)
    renderer = ResourceTreeLoadingIndicatorRenderer()

    track_color = renderer._resolved_track_color(palette, selected=False)
    selected_track_color = renderer._resolved_track_color(
        palette,
        selected=True,
    )

    assert renderer._resolved_arc_color(palette, selected=False) == text_color
    assert (
        renderer._resolved_arc_color(palette, selected=True)
        == highlighted_text_color
    )
    assert track_color != text_color
    assert track_color != base_color
    assert track_color.alpha() == renderer.TRACK_ALPHA
    assert selected_track_color != highlighted_text_color
    assert selected_track_color != highlight_color
    assert selected_track_color.alpha() == renderer.TRACK_ALPHA
    assert renderer._pen_width == renderer.PEN_WIDTH


def test_resource_item_uses_ui_kit_resource_icon(monkeypatch) -> None:
    expected_icon = QIcon()
    resource = _resource()
    calls = []

    def fake_resource_icon(ngw_resource):
        calls.append(ngw_resource)
        return expected_icon

    monkeypatch.setattr(
        "nextgis_connect.legacy.tree_widget.item.ngw_resource_icon",
        fake_resource_icon,
    )

    item = QNGWResourceItem(resource)

    assert calls == [resource]
    assert item.data(Qt.ItemDataRole.DecorationRole) is expected_icon


def test_locked_resource_item_stays_enabled_with_muted_text_color(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    text_color = QColor("#102030")
    window_color = QColor("#f0f0f0")
    disabled_text_color = QColor("#777777")
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Window, window_color)
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        disabled_text_color,
    )

    def system_palette(palette_arg=None):
        return QPalette(palette if palette_arg is None else palette_arg)

    monkeypatch.setattr(
        NextgisDecorator,
        "system_palette",
        staticmethod(system_palette),
    )

    model = QNGWResourceTreeModelBase()
    item = QNGWResourceItem(_resource())
    model.root_item.addChild(item)
    index = model.index(0, 0, QModelIndex())
    job = _Job()

    model._lockIndexByJob([index], job)

    flags = model.flags(index)
    assert flags & Qt.ItemFlag.ItemIsEnabled
    assert flags & Qt.ItemFlag.ItemIsSelectable

    foreground = model.data(index, Qt.ItemDataRole.ForegroundRole)
    assert isinstance(foreground, QBrush)
    assert foreground.color() == mix_colors(
        text_color,
        window_color,
        model._LOCKED_ITEM_TEXT_FADE,
    )
    assert foreground.color() != disabled_text_color

    model._unlockIndexesByJob(job)

    assert model.data(index, Qt.ItemDataRole.ForegroundRole).isNull()
