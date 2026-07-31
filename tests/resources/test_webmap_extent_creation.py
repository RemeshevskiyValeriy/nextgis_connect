from unittest import mock

import pytest
from qgis.core import QgsCoordinateReferenceSystem, QgsProject, QgsRectangle

from nextgis_connect.legacy.ngw.core import NGWVectorLayer, NGWWebMap
from nextgis_connect.legacy.ngw.core.ngw_webmap import NGWWebMapLayer
from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    MapForLayerCreater,
    QGISProjectUploader,
)
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job import (
    NGWCreateMapForStyle,
)

QUADRANT_EXTENTS = [
    pytest.param((10, 20, 30, 40), id="north-east"),
    pytest.param((-30, 20, -10, 40), id="north-west"),
    pytest.param((-30, -40, -10, -20), id="south-west"),
    pytest.param((10, -40, 30, -20), id="south-east"),
]
REPORTED_WEB_MERCATOR_BBOX = (
    80.733005159807,
    51.125765297828714,
    82.29183861012281,
    51.655209179236756,
)


def _reported_web_mercator_rectangle():
    return QgsRectangle(
        8987157.0246004443615675,
        6643570.37114027142524719,
        9160685.57052112184464931,
        6738021.34575835801661015,
    )


def _extent_response(coordinates):
    left, bottom, right, top = coordinates

    return {
        "extent": {
            "minLon": left,
            "minLat": bottom,
            "maxLon": right,
            "maxLat": top,
        }
    }


def _webmap_resource_json(resource_id):
    return {
        "resource": {
            "id": resource_id,
            "cls": NGWWebMap.type_id,
            "display_name": "Map",
            "description": None,
            "parent": None,
            "owner_user": None,
            "children": False,
            "interfaces": [],
        },
        "webmap": {
            "root_item": {
                "children": [],
            },
        },
    }


def _assert_bbox(bbox, coordinates) -> None:
    left, bottom, right, top = coordinates

    assert bbox["extent_left"] == pytest.approx(left)
    assert bbox["extent_bottom"] == pytest.approx(bottom)
    assert bbox["extent_right"] == pytest.approx(right)
    assert bbox["extent_top"] == pytest.approx(top)


@pytest.mark.parametrize("coordinates", QUADRANT_EXTENTS)
def test_create_webmap_uses_canvas_extent(
    qgis_app,
    coordinates,
) -> None:
    del qgis_app

    left, bottom, right, top = coordinates
    canvas = mock.Mock()
    canvas.extent.return_value = QgsRectangle(left, bottom, right, top)
    canvas.mapSettings.return_value.destinationCrs.return_value = (
        QgsCoordinateReferenceSystem.fromEpsgId(4326)
    )
    iface = mock.Mock()
    iface.mapCanvas.return_value = canvas

    uploader = QGISProjectUploader("Group", mock.Mock(), iface, None)
    webmap_layer = NGWWebMapLayer(
        42,
        "Layer",
        is_visible=True,
        transparency=None,
        legend=True,
    )

    with mock.patch.object(
        uploader,
        "_layer_status",
    ), mock.patch.object(
        NGWWebMap,
        "create_in_group",
        return_value=mock.Mock(),
    ) as create_in_group_mock:
        uploader.create_webmap(
            mock.Mock(),
            "Map",
            [webmap_layer],
            [],
        )

    _assert_bbox(create_in_group_mock.call_args.args[4], coordinates)


def test_create_webmap_transforms_canvas_extent_from_web_mercator(
    qgis_app,
) -> None:
    del qgis_app

    canvas = mock.Mock()
    canvas.extent.return_value = _reported_web_mercator_rectangle()
    canvas.mapSettings.return_value.destinationCrs.return_value = (
        QgsCoordinateReferenceSystem.fromEpsgId(3857)
    )
    iface = mock.Mock()
    iface.mapCanvas.return_value = canvas

    uploader = QGISProjectUploader("Group", mock.Mock(), iface, None)
    webmap_layer = NGWWebMapLayer(
        42,
        "Layer",
        is_visible=True,
        transparency=None,
        legend=True,
    )

    with mock.patch.object(
        uploader,
        "_layer_status",
    ), mock.patch.object(
        NGWWebMap,
        "create_in_group",
        return_value=mock.Mock(),
    ) as create_in_group_mock:
        uploader.create_webmap(
            mock.Mock(),
            "Map",
            [webmap_layer],
            [],
        )

    _assert_bbox(
        create_in_group_mock.call_args.args[4],
        REPORTED_WEB_MERCATOR_BBOX,
    )


def test_create_webmap_falls_back_to_project_crs_for_projected_extent(
    qgis_app,
) -> None:
    del qgis_app

    project = QgsProject.instance()
    previous_crs = project.crs()
    project.setCrs(QgsCoordinateReferenceSystem.fromEpsgId(3857))

    canvas = mock.Mock()
    canvas.extent.return_value = _reported_web_mercator_rectangle()
    canvas.mapSettings.return_value.destinationCrs.return_value = (
        QgsCoordinateReferenceSystem.fromEpsgId(4326)
    )
    iface = mock.Mock()
    iface.mapCanvas.return_value = canvas

    uploader = QGISProjectUploader("Group", mock.Mock(), iface, None)
    webmap_layer = NGWWebMapLayer(
        42,
        "Layer",
        is_visible=True,
        transparency=None,
        legend=True,
    )

    try:
        with mock.patch.object(
            uploader,
            "_layer_status",
        ), mock.patch.object(
            NGWWebMap,
            "create_in_group",
            return_value=mock.Mock(),
        ) as create_in_group_mock:
            uploader.create_webmap(
                mock.Mock(),
                "Map",
                [webmap_layer],
                [],
            )
    finally:
        project.setCrs(previous_crs)

    _assert_bbox(
        create_in_group_mock.call_args.args[4],
        REPORTED_WEB_MERCATOR_BBOX,
    )


@pytest.mark.parametrize("coordinates", QUADRANT_EXTENTS)
def test_create_map_for_layer_uses_ngw_extent_endpoint(
    qgis_app,
    coordinates,
) -> None:
    del qgis_app

    ngw_group = mock.Mock()
    ngw_layer = mock.Mock(spec=NGWVectorLayer)
    ngw_layer.connection.get.return_value = _extent_response(coordinates)
    ngw_layer.display_name = "Layer"
    ngw_layer.get_parent.return_value = ngw_group
    ngw_layer.resource_id = 42
    ngw_layer.type_id = NGWVectorLayer.type_id

    job = MapForLayerCreater(ngw_layer, 100)

    with mock.patch.object(
        job,
        "unique_resource_name",
        return_value="Layer-map",
    ), mock.patch.object(
        NGWWebMap,
        "create_in_group",
        return_value=mock.Mock(),
    ) as create_in_group_mock:
        job.create4VectorRasterLayer()

    ngw_layer.connection.get.assert_called_once_with("/api/resource/42/extent")
    _assert_bbox(create_in_group_mock.call_args.kwargs["bbox"], coordinates)


@pytest.mark.parametrize("coordinates", QUADRANT_EXTENTS)
def test_create_map_for_style_uses_ngw_extent_endpoint(
    qgis_app,
    coordinates,
) -> None:
    del qgis_app

    ngw_group = mock.Mock()
    ngw_layer = mock.Mock(spec=NGWVectorLayer)
    ngw_layer.connection.get.return_value = _extent_response(coordinates)
    ngw_layer.display_name = "Layer"
    ngw_layer.get_parent.return_value = ngw_group
    ngw_layer.resource_id = 42
    ngw_style = mock.Mock()
    ngw_style.display_name = "Style"
    ngw_style.get_parent.return_value = ngw_layer
    ngw_style.resource_id = 100

    job = NGWCreateMapForStyle(ngw_style)

    with mock.patch.object(
        job,
        "unique_resource_name",
        return_value="Style-map",
    ), mock.patch.object(
        NGWWebMap,
        "create_in_group",
        return_value=mock.Mock(),
    ) as create_in_group_mock:
        job._do()

    ngw_layer.connection.get.assert_called_once_with("/api/resource/42/extent")
    _assert_bbox(create_in_group_mock.call_args.kwargs["bbox"], coordinates)


def test_create_in_group_preserves_world_extent(qgis_app) -> None:
    del qgis_app

    connection = mock.Mock()
    connection.post.return_value = {"id": 100}
    connection.get.return_value = _webmap_resource_json(100)
    resource_factory = mock.Mock()
    resource_factory.connection = connection
    ngw_group = mock.Mock()
    ngw_group.get_api_collection_url.return_value = "/api/resource/"
    ngw_group.res_factory = resource_factory
    ngw_group.resource_id = 1

    NGWWebMap.create_in_group(
        "Map",
        ngw_group,
        [],
        [],
        bbox=None,
    )

    params = connection.post.call_args.kwargs["params"]
    bbox = params["webmap"]

    _assert_bbox(bbox, (-180.0, -90.0, 180.0, 90.0))


def test_create_in_group_does_not_normalize_projected_values(qgis_app) -> None:
    del qgis_app

    rectangle = _reported_web_mercator_rectangle()
    connection = mock.Mock()
    connection.post.return_value = {"id": 100}
    connection.get.return_value = _webmap_resource_json(100)
    resource_factory = mock.Mock()
    resource_factory.connection = connection
    ngw_group = mock.Mock()
    ngw_group.get_api_collection_url.return_value = "/api/resource/"
    ngw_group.res_factory = resource_factory
    ngw_group.resource_id = 1

    NGWWebMap.create_in_group(
        "Map",
        ngw_group,
        [],
        [],
        bbox={
            "extent_left": rectangle.xMinimum(),
            "extent_bottom": rectangle.yMinimum(),
            "extent_right": rectangle.xMaximum(),
            "extent_top": rectangle.yMaximum(),
        },
    )

    params = connection.post.call_args.kwargs["params"]
    bbox = params["webmap"]

    _assert_bbox(bbox, (-180.0, -90.0, 180.0, 90.0))
