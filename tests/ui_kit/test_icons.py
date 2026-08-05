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

from qgis.PyQt.QtWidgets import QLabel

from nextgis_connect.ui_kit.icons import (
    draw_icon,
    draw_svg_icon,
    material_icon,
    plugin_icon_file_path,
)


class _HighDpiLabel(QLabel):
    def devicePixelRatioF(self) -> float:
        return 2.0


def test_draw_svg_icon_uses_device_pixel_ratio(qgis_app) -> None:
    del qgis_app

    label = _HighDpiLabel()

    pixmap = draw_svg_icon(
        label,
        plugin_icon_file_path("attachments/unknown.svg"),
        size=64,
    )

    assert not pixmap.isNull()
    assert pixmap.devicePixelRatio() == 2.0
    assert pixmap.width() == 128
    assert pixmap.height() == 128
    assert label.pixmap() is not None

    label.deleteLater()


def test_draw_icon_uses_device_pixel_ratio(qgis_app) -> None:
    del qgis_app

    label = _HighDpiLabel()

    pixmap = draw_icon(label, material_icon("check", size=16), size=16)

    assert not pixmap.isNull()
    assert pixmap.devicePixelRatio() == 2.0
    assert pixmap.width() == 16
    assert pixmap.height() == 16
    assert label.pixmap() is not None

    label.deleteLater()
