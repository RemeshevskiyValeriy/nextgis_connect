from types import SimpleNamespace

from qgis.PyQt.QtCore import QModelIndex, Qt
from qgis.PyQt.QtGui import QBrush, QColor, QPalette

from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModelBase
from nextgis_connect.ui_kit.rendering.graphics import (
    NextgisDecorator,
    mix_colors,
)


class _Job:
    def error(self):
        return None


def _resource(resource_id: int = 1):
    return SimpleNamespace(
        display_name="Resource",
        icon_path="",
        resource_id=resource_id,
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
    assert default_icon.isNull()

    model._lockIndexByJob([index], job)

    loading_icon = model.data(index, Qt.ItemDataRole.DecorationRole)
    assert not loading_icon.isNull()

    model._unlockIndexesByJob(job)

    restored_icon = model.data(index, Qt.ItemDataRole.DecorationRole)
    assert restored_icon.isNull()


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
