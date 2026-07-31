import math

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsRectangle,
    QgsReferencedRectangle,
)

from nextgis_connect.platform.qgis.extent_calculator import (
    ExtentCalculator,
)


def _crs(epsg_id: int) -> QgsCoordinateReferenceSystem:
    return QgsCoordinateReferenceSystem.fromEpsgId(epsg_id)


QUADRANT_EXTENTS = [
    pytest.param((10, 20, 30, 40), id="north-east"),
    pytest.param((-30, 20, -10, 40), id="north-west"),
    pytest.param((-30, -40, -10, -20), id="south-west"),
    pytest.param((10, -40, 30, -20), id="south-east"),
]
WEB_MERCATOR_RADIUS = 6378137.0
REPORTED_WEB_MERCATOR_RECTANGLE = QgsRectangle(
    8987157.0246004443615675,
    6643570.37114027142524719,
    9160685.57052112184464931,
    6738021.34575835801661015,
)
REPORTED_WEB_MERCATOR_BBOX = (
    80.733005159807,
    51.125765297828714,
    82.29183861012281,
    51.655209179236756,
)


def _web_mercator_x(longitude: float) -> float:
    return WEB_MERCATOR_RADIUS * math.radians(longitude)


def _web_mercator_y(latitude: float) -> float:
    latitude_radians = math.radians(latitude)

    return WEB_MERCATOR_RADIUS * math.log(
        math.tan((math.pi / 4.0) + (latitude_radians / 2.0))
    )


def _web_mercator_rectangle(coordinates) -> QgsRectangle:
    left, bottom, right, top = coordinates

    return QgsRectangle(
        _web_mercator_x(left),
        _web_mercator_y(bottom),
        _web_mercator_x(right),
        _web_mercator_y(top),
    )


def test_from_ngw_extent_dict(qgis_app) -> None:
    del qgis_app

    extent = ExtentCalculator.from_ngw_extent_dict(
        {
            "extent": {
                "minLon": 30,
                "maxLon": 10,
                "minLat": 40,
                "maxLat": 20,
            }
        }
    )

    assert extent is not None
    assert extent.crs().authid() == "EPSG:4326"
    assert extent.xMinimum() == pytest.approx(10.0)
    assert extent.yMinimum() == pytest.approx(20.0)
    assert extent.xMaximum() == pytest.approx(30.0)
    assert extent.yMaximum() == pytest.approx(40.0)


def test_from_ngw_extent_tuple(qgis_app) -> None:
    del qgis_app

    extent = ExtentCalculator.from_ngw_extent_tuple((30, 10, 40, 20))

    assert extent is not None
    assert extent.crs().authid() == "EPSG:4326"
    assert extent.xMinimum() == pytest.approx(10.0)
    assert extent.yMinimum() == pytest.approx(20.0)
    assert extent.xMaximum() == pytest.approx(30.0)
    assert extent.yMaximum() == pytest.approx(40.0)


def test_from_webmap_extent_dict(qgis_app) -> None:
    del qgis_app

    extent = ExtentCalculator.from_webmap_extent_dict(
        {
            "extent_left": 10,
            "extent_bottom": 20,
            "extent_right": 30,
            "extent_top": 40,
        }
    )

    assert extent is not None
    assert extent.crs().authid() == "EPSG:4326"
    assert extent.xMinimum() == pytest.approx(10.0)
    assert extent.yMinimum() == pytest.approx(20.0)
    assert extent.xMaximum() == pytest.approx(30.0)
    assert extent.yMaximum() == pytest.approx(40.0)


@pytest.mark.parametrize(
    "response",
    [
        {},
        {"extent": None},
        {"extent": {"minLon": 1, "minLat": 2, "maxLon": 3}},
        {"extent": {"minLon": math.inf, "minLat": 2, "maxLon": 3}},
    ],
)
def test_from_ngw_extent_dict_rejects_invalid_values(
    qgis_app,
    response,
) -> None:
    del qgis_app

    assert ExtentCalculator.from_ngw_extent_dict(response) is None


@pytest.mark.parametrize(
    "extent",
    [
        {
            "extent": {
                "minLon": 8987157,
                "minLat": 6643570,
                "maxLon": 9160685,
                "maxLat": 6738021,
            }
        },
        (8987157, 9160685, 6643570, 6738021),
        {
            "extent_left": 8987157,
            "extent_bottom": 6643570,
            "extent_right": 9160685,
            "extent_top": 6738021,
        },
    ],
)
def test_geographic_inputs_reject_projected_values(
    qgis_app,
    extent,
) -> None:
    del qgis_app

    if isinstance(extent, tuple):
        result = ExtentCalculator.from_ngw_extent_tuple(extent)
    elif "extent_left" in extent:
        result = ExtentCalculator.from_webmap_extent_dict(extent)
    else:
        result = ExtentCalculator.from_ngw_extent_dict(extent)

    assert result is None


def test_from_qgs_rectangle_rejects_null_rectangle(qgis_app) -> None:
    del qgis_app

    extent = ExtentCalculator.from_qgs_rectangle(QgsRectangle(), _crs(4326))

    assert extent is None


def test_from_qgs_rectangle_rejects_projected_values_in_geographic_crs(
    qgis_app,
) -> None:
    del qgis_app

    extent = ExtentCalculator.from_qgs_rectangle(
        REPORTED_WEB_MERCATOR_RECTANGLE,
        _crs(4326),
    )

    assert extent is None


def test_to_webmap_extent_rejects_projected_values_in_geographic_crs(
    qgis_app,
) -> None:
    del qgis_app

    extent = QgsReferencedRectangle(
        REPORTED_WEB_MERCATOR_RECTANGLE, _crs(4326)
    )

    with pytest.raises(ValueError):
        ExtentCalculator.to_webmap_extent(extent)


def test_combine_extents(qgis_app) -> None:
    del qgis_app

    target_crs = _crs(4326)
    extent = ExtentCalculator.combine(
        [
            QgsReferencedRectangle(QgsRectangle(10, 20, 30, 40), target_crs),
            QgsReferencedRectangle(QgsRectangle(-10, 30, 15, 50), target_crs),
        ],
        target_crs,
    )

    assert extent is not None
    assert extent.xMinimum() == pytest.approx(-10)
    assert extent.yMinimum() == pytest.approx(20)
    assert extent.xMaximum() == pytest.approx(30)
    assert extent.yMaximum() == pytest.approx(50)


def test_to_webmap_extent_transforms_to_wgs84(qgis_app) -> None:
    del qgis_app

    extent = QgsReferencedRectangle(
        QgsRectangle(
            0.0,
            0.0,
            1113194.9079327357,
            1118889.9748579594,
        ),
        _crs(3857),
    )

    webmap_extent = ExtentCalculator.to_webmap_extent(extent)

    assert webmap_extent["extent_left"] == pytest.approx(0.0)
    assert webmap_extent["extent_bottom"] == pytest.approx(0.0)
    assert webmap_extent["extent_right"] == pytest.approx(10.0)
    assert webmap_extent["extent_top"] == pytest.approx(10.0)


def test_from_canvas_extent_uses_fallback_for_projected_values(
    qgis_app,
) -> None:
    del qgis_app

    extent = ExtentCalculator.from_canvas_extent(
        REPORTED_WEB_MERCATOR_RECTANGLE,
        _crs(4326),
        _crs(3857),
    )

    assert extent is not None
    assert extent.crs().authid() == "EPSG:3857"

    webmap_extent = ExtentCalculator.to_webmap_extent(extent)
    left, bottom, right, top = REPORTED_WEB_MERCATOR_BBOX

    assert webmap_extent["extent_left"] == pytest.approx(left)
    assert webmap_extent["extent_bottom"] == pytest.approx(bottom)
    assert webmap_extent["extent_right"] == pytest.approx(right)
    assert webmap_extent["extent_top"] == pytest.approx(top)


def test_from_canvas_extent_detects_web_mercator_values(
    qgis_app,
) -> None:
    del qgis_app

    extent = ExtentCalculator.from_canvas_extent(
        REPORTED_WEB_MERCATOR_RECTANGLE,
        _crs(4326),
        _crs(4326),
    )

    assert extent is not None
    assert extent.crs().authid() == "EPSG:3857"

    webmap_extent = ExtentCalculator.to_webmap_extent(extent)
    left, bottom, right, top = REPORTED_WEB_MERCATOR_BBOX

    assert webmap_extent["extent_left"] == pytest.approx(left)
    assert webmap_extent["extent_bottom"] == pytest.approx(bottom)
    assert webmap_extent["extent_right"] == pytest.approx(right)
    assert webmap_extent["extent_top"] == pytest.approx(top)


@pytest.mark.parametrize("coordinates", QUADRANT_EXTENTS)
def test_to_webmap_extent_keeps_quadrant_signs(
    qgis_app,
    coordinates,
) -> None:
    del qgis_app

    left, bottom, right, top = coordinates
    extent = QgsReferencedRectangle(
        QgsRectangle(left, bottom, right, top),
        _crs(4326),
    )

    webmap_extent = ExtentCalculator.to_webmap_extent(extent)

    assert webmap_extent["extent_left"] == pytest.approx(left)
    assert webmap_extent["extent_bottom"] == pytest.approx(bottom)
    assert webmap_extent["extent_right"] == pytest.approx(right)
    assert webmap_extent["extent_top"] == pytest.approx(top)


@pytest.mark.parametrize("coordinates", QUADRANT_EXTENTS)
def test_to_webmap_extent_transforms_quadrants_from_web_mercator(
    qgis_app,
    coordinates,
) -> None:
    del qgis_app

    left, bottom, right, top = coordinates
    extent = QgsReferencedRectangle(
        _web_mercator_rectangle(coordinates),
        _crs(3857),
    )

    webmap_extent = ExtentCalculator.to_webmap_extent(extent)

    assert webmap_extent["extent_left"] == pytest.approx(left)
    assert webmap_extent["extent_bottom"] == pytest.approx(bottom)
    assert webmap_extent["extent_right"] == pytest.approx(right)
    assert webmap_extent["extent_top"] == pytest.approx(top)
