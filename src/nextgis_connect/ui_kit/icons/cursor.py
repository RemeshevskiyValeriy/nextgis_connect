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

import math
from dataclasses import dataclass
from enum import Enum

from qgis.core import Qgis, QgsApplication
from qgis.PyQt.QtGui import QCursor, QFontMetrics

from nextgis_connect.ui_kit.icons.icon import plugin_icon


@dataclass
class _CursorMetadata:
    """Store cursor icon metadata.

    Keep the icon path and active point used to build a themed Qt cursor.

    :param icon: Path to the cursor icon.
    :param active_x: X-coordinate of the cursor's active point.
    :param active_y: Y-coordinate of the cursor's active point.
    """

    icon: str
    active_x: int
    active_y: int


class NgConnectCursor(Enum):
    """Define available cursors for the NextGIS Connect plugin.

    :cvar IDENTIFY: Cursor for the "Identify" tool.
    """

    IDENTIFY = _CursorMetadata("cursors/identification.svg", 3, 6)


def create_cursor(cursor_metadata: NgConnectCursor) -> QCursor:
    """Create a QCursor from cursor metadata.

    Create a scaled cursor using the icon and active point specified by
    the cursor metadata. The scaling logic follows QgsApplication theme
    cursor behavior.

    :param cursor_metadata: The cursor type to generate.
    :return: A QCursor object for the specified cursor type.
    """
    DEFAULT_ICON_SIZE = 32.0

    icon = plugin_icon(cursor_metadata.value.icon)
    if icon is None or icon.isNull():
        return QCursor()

    font_metrics = QFontMetrics(QgsApplication.font())
    scale = Qgis.UI_SCALE_FACTOR * font_metrics.height() / DEFAULT_ICON_SIZE
    cursor = QCursor(
        icon.pixmap(
            math.ceil(DEFAULT_ICON_SIZE * scale),
            math.ceil(DEFAULT_ICON_SIZE * scale),
        ),
        math.ceil(cursor_metadata.value.active_x * scale),
        math.ceil(cursor_metadata.value.active_y * scale),
    )

    return cursor
