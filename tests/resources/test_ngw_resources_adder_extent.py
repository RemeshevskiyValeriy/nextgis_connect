from unittest import mock

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem,
    QgsFeature,
    QgsGeometry,
    QgsMapLayer,
    QgsPointXY,
    QgsProject,
    QgsVectorLayer,
)

from nextgis_connect.legacy.ngw_resources_adder import NgwResourcesAdder


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


def _prepared_adder(layers):
    adder = NgwResourcesAdder.__new__(NgwResourcesAdder)
    adder._NgwResourcesAdder__project = QgsProject.instance()
    adder._NgwResourcesAdder__extent_layers = layers
    adder._NgwResourcesAdder__extent_resource_ids_by_layer_id = {}
    adder._NgwResourcesAdder__model = mock.Mock()
    return adder


def _run_extent_update(adder, target_crs):
    canvas = mock.Mock()
    canvas.mapSettings.return_value.destinationCrs.return_value = target_crs

    with mock.patch(
        "nextgis_connect.legacy.ngw_resources_adder.iface",
    ) as iface_mock, mock.patch(
        "nextgis_connect.legacy.ngw_resources_adder.QTimer.singleShot",
        side_effect=lambda _timeout, callback: callback(),
    ):
        iface_mock.mapCanvas.return_value = canvas
        adder._NgwResourcesAdder__set_added_layers_extent()

    return canvas


def test_set_added_layers_extent_combines_qgis_layer_extents(
    qgis_app,
) -> None:
    del qgis_app

    adder = _prepared_adder(
        [
            _point_layer("first", 10, 20),
            _point_layer("second", -10, 40),
        ]
    )

    canvas = _run_extent_update(adder, _crs(4326))

    referenced_extent = canvas.setReferencedExtent.call_args.args[0]
    assert referenced_extent.xMinimum() == pytest.approx(-10)
    assert referenced_extent.yMinimum() == pytest.approx(20)
    assert referenced_extent.xMaximum() == pytest.approx(10)
    assert referenced_extent.yMaximum() == pytest.approx(40)
    assert referenced_extent.crs().authid() == "EPSG:4326"
    canvas.refresh.assert_called_once()


def test_set_added_layers_extent_uses_ngw_endpoint_as_fallback(
    qgis_app,
) -> None:
    del qgis_app

    layer = mock.Mock(spec=QgsMapLayer)
    layer.id.return_value = "layer-id"
    layer.isValid.return_value = False

    resource = mock.Mock()
    resource.connection.get.return_value = {
        "extent": {
            "minLon": 10,
            "minLat": 20,
            "maxLon": 30,
            "maxLat": 40,
        }
    }

    adder = _prepared_adder([layer])
    adder._NgwResourcesAdder__model.resource.return_value = resource
    adder._NgwResourcesAdder__extent_resource_ids_by_layer_id = {
        "layer-id": ("connection-id", 42)
    }

    canvas = _run_extent_update(adder, _crs(4326))

    resource.connection.get.assert_called_once_with("/api/resource/42/extent")
    referenced_extent = canvas.setReferencedExtent.call_args.args[0]
    assert referenced_extent.xMinimum() == pytest.approx(10)
    assert referenced_extent.yMinimum() == pytest.approx(20)
    assert referenced_extent.xMaximum() == pytest.approx(30)
    assert referenced_extent.yMaximum() == pytest.approx(40)


def test_set_added_layers_extent_prefers_ngw_endpoint_for_ngw_layer(
    qgis_app,
) -> None:
    del qgis_app

    layer = _point_layer("zero", 0, 0)

    resource = mock.Mock()
    resource.connection.get.return_value = {
        "extent": {
            "minLon": 10,
            "minLat": 20,
            "maxLon": 30,
            "maxLat": 40,
        }
    }

    adder = _prepared_adder([layer])
    adder._NgwResourcesAdder__model.resource.return_value = resource
    adder._NgwResourcesAdder__extent_resource_ids_by_layer_id = {
        layer.id(): ("connection-id", 42)
    }

    canvas = _run_extent_update(adder, _crs(4326))

    resource.connection.get.assert_called_once_with("/api/resource/42/extent")
    referenced_extent = canvas.setReferencedExtent.call_args.args[0]
    assert referenced_extent.xMinimum() == pytest.approx(10)
    assert referenced_extent.yMinimum() == pytest.approx(20)
    assert referenced_extent.xMaximum() == pytest.approx(30)
    assert referenced_extent.yMaximum() == pytest.approx(40)
