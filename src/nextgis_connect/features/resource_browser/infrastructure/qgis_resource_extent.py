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

import json
from abc import ABC, abstractmethod
from typing import Optional

from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsMapLayer,
    QgsNetworkAccessManager,
    QgsRectangle,
    QgsReferencedRectangle,
)
from qgis.gui import QgsMapCanvas
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QTimer, QUrl
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from nextgis_connect.features.resource_browser.domain import (
    ResourceImportExtent,
    ResourceImportSource,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.extent_calculator import ExtentCalculator


class ResourceExtentProvider(ABC):
    """Load a referenced extent for a neutral Web GIS resource source."""

    @abstractmethod
    def fetch(
        self,
        source: ResourceImportSource,
    ) -> Optional[QgsReferencedRectangle]:
        """Return the source resource extent, if the response contains one."""


class QgisNetworkResourceExtentProvider(ResourceExtentProvider):
    """Load a resource extent using the QGIS network and auth stack."""

    def fetch(
        self,
        source: ResourceImportSource,
    ) -> Optional[QgsReferencedRectangle]:
        request = QNetworkRequest(QUrl(self._extent_url(source)))
        response = QgsNetworkAccessManager.blockingGet(
            request,
            source.auth_config_id or "",
            False,
        )
        if response.error() != QNetworkReply.NetworkError.NoError:
            raise RuntimeError(response.errorString())

        try:
            payload = json.loads(bytes(response.content()).decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise RuntimeError("Web GIS returned an invalid extent") from error

        return ExtentCalculator.from_ngw_extent_dict(payload)

    def _extent_url(self, source: ResourceImportSource) -> str:
        return (
            f"{source.connection_url.rstrip('/')}"
            f"/api/resource/{source.resource_id}/extent"
        )


class QgisLayerSourceExtentApplicator:
    """Apply a Web GIS source extent to its QGIS representation."""

    def __init__(
        self,
        extent_provider: Optional[ResourceExtentProvider] = None,
    ) -> None:
        self._extent_provider = (
            extent_provider or QgisNetworkResourceExtentProvider()
        )

    def apply(
        self,
        source: ResourceImportSource,
        layer: QgsMapLayer,
    ) -> bool:
        """Apply a transformed source extent without failing layer import."""
        source_extent = self.fetch_source_extent(source)
        if source_extent is None:
            return False

        return self.apply_referenced_extent(source_extent, layer)

    def fetch_source_extent(
        self,
        source: ResourceImportSource,
    ) -> Optional[QgsReferencedRectangle]:
        """Fetch a source extent without failing layer import."""
        try:
            return self._extent_provider.fetch(source)
        except Exception:
            logger.exception(
                f"Could not apply extent for Web GIS resource "
                f"{source.resource_id}"
            )
            return None

    def apply_import_extent(
        self,
        source_extent: ResourceImportExtent,
        layer: QgsMapLayer,
    ) -> bool:
        """Apply an extent already supplied by the import request."""
        referenced_extent = self.create_import_extent(source_extent)
        if referenced_extent is None:
            return False

        return self.apply_referenced_extent(referenced_extent, layer)

    def create_import_extent(
        self,
        source_extent: ResourceImportExtent,
    ) -> Optional[QgsReferencedRectangle]:
        """Create a referenced extent from neutral import data."""
        try:
            return self._create_referenced_extent(source_extent)
        except Exception:
            logger.exception("Could not apply Web GIS import extent")
            return None

    def apply_referenced_extent(
        self,
        source_extent: QgsReferencedRectangle,
        layer: QgsMapLayer,
    ) -> bool:
        """Apply a referenced source extent to the given layer."""
        try:
            return self._apply_referenced_extent(source_extent, layer)
        except Exception:
            logger.exception("Could not apply Web GIS layer extent")
            return False

    def _apply_referenced_extent(
        self,
        source_extent: QgsReferencedRectangle,
        layer: QgsMapLayer,
    ) -> bool:
        layer_extent = ExtentCalculator.transform(
            source_extent,
            layer.crs(),
        )
        if layer_extent is None:
            return False

        layer.setExtent(layer_extent)
        return True

    def _create_referenced_extent(
        self,
        source_extent: ResourceImportExtent,
    ) -> Optional[QgsReferencedRectangle]:
        crs = QgsCoordinateReferenceSystem(
            source_extent.coordinate_reference_system_auth_id
        )
        if not crs.isValid():
            return None

        rectangle = QgsRectangle(
            source_extent.x_min,
            source_extent.y_min,
            source_extent.x_max,
            source_extent.y_max,
        )
        return QgsReferencedRectangle(rectangle, crs)


class QgisMapCanvasExtentApplicator:
    """Apply a source extent to the current QGIS map canvas."""

    def __init__(
        self,
        canvas: Optional[QgsMapCanvas] = None,
    ) -> None:
        self._canvas = canvas

    def apply(
        self,
        source_extent: QgsReferencedRectangle,
    ) -> bool:
        """Buffer and schedule an extent after layer-tree insertion events."""
        if self._canvas is None:
            return False

        buffered_extent = ExtentCalculator.buffered(source_extent)
        if buffered_extent is None:
            buffered_extent = source_extent

        QTimer.singleShot(
            0,
            lambda: self._apply_on_canvas(buffered_extent),
        )
        return True

    def _apply_on_canvas(
        self,
        source_extent: QgsReferencedRectangle,
    ) -> bool:
        try:
            if not self._is_canvas_available():
                return False

            self._canvas.setReferencedExtent(source_extent)
            self._canvas.refresh()
            return True
        except Exception:
            logger.exception("Could not apply Web GIS extent to map canvas")
            return False

    def _is_canvas_available(self) -> bool:
        if self._canvas is None:
            return False

        try:
            return not sip.isdeleted(self._canvas)
        except TypeError:
            return True
