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

from typing import List, Optional
from unittest import mock

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsPointXY,
    QgsRectangle,
    QgsReferencedRectangle,
    QgsVectorLayer,
)

from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_batch_extent import (
    BboxLayerExtentStrategy,
    BboxResourceExtentProvider,
    CachedVectorExtentStrategy,
    QgisResourceBatchExtentCoordinator,
    ResourceExtentKey,
    ResourceExtentKind,
    ResourceExtentResolver,
    ResourceExtentSubject,
    WebMapExtentStrategy,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_extent import (
    QgisMapCanvasExtentApplicator,
)


def _crs(epsg_id: int) -> QgsCoordinateReferenceSystem:
    return QgsCoordinateReferenceSystem.fromEpsgId(epsg_id)


def _point_layer(name: str, x: float, y: float) -> QgsVectorLayer:
    layer = QgsVectorLayer("Point?crs=EPSG:4326", name, "memory")
    assert layer.isValid()

    feature = QgsFeature(layer.fields())
    feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(x, y)))
    layer.dataProvider().addFeatures([feature])
    layer.updateExtents()
    return layer


def _extent(
    x_min: float,
    y_min: float,
    x_max: float,
    y_max: float,
) -> QgsReferencedRectangle:
    return QgsReferencedRectangle(
        QgsRectangle(x_min, y_min, x_max, y_max),
        _crs(4326),
    )


class _RecordingExtentProvider(BboxResourceExtentProvider):
    def __init__(
        self,
        extent: Optional[QgsReferencedRectangle],
        error: Optional[Exception] = None,
    ) -> None:
        self.extent = extent
        self.error = error
        self.keys: List[ResourceExtentKey] = []

    def fetch(
        self,
        key: ResourceExtentKey,
    ) -> Optional[QgsReferencedRectangle]:
        self.keys.append(key)
        if self.error is not None:
            raise self.error
        return self.extent


def _resolver(
    provider: BboxResourceExtentProvider,
) -> ResourceExtentResolver:
    return ResourceExtentResolver(
        (
            WebMapExtentStrategy(),
            CachedVectorExtentStrategy(),
            BboxLayerExtentStrategy(provider),
        )
    )


def test_cached_vector_uses_local_layer_even_with_bbox_interface(
    qgis_app,
) -> None:
    del qgis_app
    provider = _RecordingExtentProvider(_extent(10, 20, 30, 40))
    subject = ResourceExtentSubject(
        key=ResourceExtentKey("connection-id", 42),
        kind=ResourceExtentKind.CACHED_VECTOR,
        interfaces=frozenset({"IBboxLayer"}),
        layer=_point_layer("Cached", 5, 6),
    )

    extents = _resolver(provider).resolve((subject,))

    assert provider.keys == []
    assert len(extents) == 1
    assert extents[0].xMinimum() == pytest.approx(5)
    assert extents[0].yMinimum() == pytest.approx(6)


def test_bbox_resource_uses_endpoint_provider(qgis_app) -> None:
    del qgis_app
    expected_extent = _extent(10, 20, 30, 40)
    provider = _RecordingExtentProvider(expected_extent)
    key = ResourceExtentKey("connection-id", 42)
    subject = ResourceExtentSubject(
        key=key,
        kind=ResourceExtentKind.RESOURCE,
        interfaces=frozenset({"IBboxLayer"}),
    )

    extents = _resolver(provider).resolve((subject,))

    assert provider.keys == [key]
    assert extents == [expected_extent]


def test_resource_without_bbox_interface_does_not_contribute_extent(
    qgis_app,
) -> None:
    del qgis_app
    provider = _RecordingExtentProvider(_extent(10, 20, 30, 40))
    subject = ResourceExtentSubject(
        key=ResourceExtentKey("connection-id", 42),
        kind=ResourceExtentKind.RESOURCE,
    )

    assert _resolver(provider).resolve((subject,)) == []
    assert provider.keys == []


def test_webmap_uses_only_its_stored_extent(qgis_app) -> None:
    del qgis_app
    webmap_extent = _extent(1, 2, 3, 4)
    provider = _RecordingExtentProvider(_extent(10, 20, 30, 40))
    subject = ResourceExtentSubject(
        key=ResourceExtentKey("connection-id", 7),
        kind=ResourceExtentKind.WEBMAP,
        interfaces=frozenset({"IBboxLayer"}),
        webmap_extent=webmap_extent,
    )

    assert _resolver(provider).resolve((subject,)) == [webmap_extent]
    assert provider.keys == []


def test_failed_extent_source_is_skipped_without_fallback(qgis_app) -> None:
    del qgis_app
    provider = _RecordingExtentProvider(None, RuntimeError("Unavailable"))
    subject = ResourceExtentSubject(
        key=ResourceExtentKey("connection-id", 42),
        kind=ResourceExtentKind.RESOURCE,
        interfaces=frozenset({"IBboxLayer"}),
        layer=_point_layer("Fallback must not be used", 5, 6),
    )

    assert _resolver(provider).resolve((subject,)) == []


def test_coordinator_combines_mixed_resource_extents(qgis_app) -> None:
    del qgis_app
    provider = _RecordingExtentProvider(_extent(10, 20, 30, 40))
    resolver = _resolver(provider)
    canvas = mock.Mock()
    canvas.mapSettings.return_value.destinationCrs.return_value = _crs(4326)
    canvas_applicator = mock.Mock(spec=QgisMapCanvasExtentApplicator)
    canvas_applicator.apply.return_value = True
    coordinator = QgisResourceBatchExtentCoordinator(
        mock.Mock(),
        canvas,
        resolver=resolver,
        canvas_applicator=canvas_applicator,
    )
    coordinator.add(
        ResourceExtentSubject(
            key=ResourceExtentKey("connection-id", 7),
            kind=ResourceExtentKind.WEBMAP,
            webmap_extent=_extent(-10, -20, 0, 0),
        )
    )
    coordinator.add(
        ResourceExtentSubject(
            key=ResourceExtentKey("connection-id", 42),
            kind=ResourceExtentKind.RESOURCE,
            interfaces=frozenset({"IBboxLayer"}),
        )
    )

    assert coordinator.apply() is True

    combined_extent = canvas_applicator.apply.call_args.args[0]
    assert combined_extent.xMinimum() == pytest.approx(-10)
    assert combined_extent.yMinimum() == pytest.approx(-20)
    assert combined_extent.xMaximum() == pytest.approx(30)
    assert combined_extent.yMaximum() == pytest.approx(40)


def test_canvas_applicator_adds_buffer_once(qgis_app) -> None:
    del qgis_app
    canvas = mock.Mock()
    applicator = QgisMapCanvasExtentApplicator(canvas)

    with mock.patch(
        "nextgis_connect.features.resource_browser.infrastructure."
        "qgis_resource_extent.QTimer.singleShot",
        side_effect=lambda _timeout, callback: callback(),
    ):
        assert applicator.apply(_extent(10, 20, 30, 40)) is True

    buffered_extent = canvas.setReferencedExtent.call_args.args[0]
    assert buffered_extent.xMinimum() == pytest.approx(9)
    assert buffered_extent.yMinimum() == pytest.approx(19)
    assert buffered_extent.xMaximum() == pytest.approx(31)
    assert buffered_extent.yMaximum() == pytest.approx(41)
    canvas.refresh.assert_called_once()
