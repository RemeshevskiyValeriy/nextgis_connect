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

from typing import Optional

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QSpacerItem,
    QWidget,
)

from nextgis_connect.ui_kit.icons import draw_icon, material_icon


class NoFeaturesWidget(QWidget):
    """Show a message when no features match the click location.

    Render an informational icon and centered text explaining that the
    identification request did not return any features.
    """

    def __init__(self, parent: Optional[QWidget] = None):
        """Initialize the placeholder widget.

        :param parent: Parent widget owning the placeholder.
        """
        super().__init__(parent)

        label = QLabel("No features were found at the click location.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        icon_size = label.fontMetrics().height()
        icon = QLabel()
        draw_icon(icon, material_icon("info"), size=icon_size)

        layout = QHBoxLayout()
        layout.addSpacerItem(
            QSpacerItem(
                40,
                20,
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
        )
        layout.addWidget(icon)
        layout.addWidget(label)
        layout.addSpacerItem(
            QSpacerItem(
                40,
                20,
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Minimum,
            )
        )
        self.setLayout(layout)
