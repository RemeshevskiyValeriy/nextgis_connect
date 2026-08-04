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

from qgis.gui import QgsLayerTreeViewIndicator
from qgis.PyQt.QtCore import QModelIndex, QObject, pyqtSignal, pyqtSlot

from nextgis_connect.features.synchronization.presentation.layer_indicator_presenter import (
    DetachedLayerIndicatorPresenter,
)


class DetachedLayerTreeIndicator(QgsLayerTreeViewIndicator):
    """Show a detached layer indicator in the QGIS layer tree."""

    details_requested = pyqtSignal(name="detailsRequested")

    def __init__(
        self,
        parent: QObject,
        presenter: DetachedLayerIndicatorPresenter,
    ) -> None:
        """Initialize layer tree indicator.

        :param parent: Parent QObject.
        :param presenter: Presenter that emits ready-to-display state.
        """
        super().__init__(parent)

        self._presenter = presenter
        self.clicked.connect(self._request_details)
        self._presenter.icon_changed.connect(self.setIcon)
        self._presenter.tooltip_changed.connect(self.setToolTip)
        self.setIcon(self._presenter.current_icon)
        self.setToolTip(self._presenter.current_tooltip)

    @pyqtSlot(QModelIndex, name="requestDetails")
    def _request_details(self, *_: object) -> None:
        self.details_requested.emit()
