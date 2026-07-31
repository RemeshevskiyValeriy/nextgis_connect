from unittest import mock

from nextgis_connect.legacy.ngw_resources_adder import NgwResourcesAdder
from nextgis_connect.legacy.tree_widget.item import QNGWResourceItem


def _create_adder() -> NgwResourcesAdder:
    adder = NgwResourcesAdder.__new__(NgwResourcesAdder)
    adder._NgwResourcesAdder__skipped_resources = set()
    adder._NgwResourcesAdder__insert_group = mock.Mock()
    adder._NgwResourcesAdder__add_service_layer = mock.Mock()
    return adder


def _create_service_index(service_resource: mock.Mock) -> mock.Mock:
    service_index = mock.Mock()
    service_index.data.return_value = service_resource
    return service_index


def test_add_service_with_single_layer_does_not_create_group() -> None:
    layer = mock.Mock()
    service_resource = mock.Mock()
    service_resource.layers = [layer]

    adder = _create_adder()
    service_index = _create_service_index(service_resource)

    adder._NgwResourcesAdder__add_service(service_index)

    adder._NgwResourcesAdder__insert_group.assert_not_called()
    adder._NgwResourcesAdder__add_service_layer.assert_called_once_with(
        service_resource, layer
    )
    service_index.data.assert_called_once_with(
        QNGWResourceItem.NGWResourceRole
    )


def test_add_service_with_multiple_layers_creates_group() -> None:
    first_layer = mock.Mock()
    second_layer = mock.Mock()
    service_resource = mock.Mock()
    service_resource.display_name = "WFS service"
    service_resource.layers = [first_layer, second_layer]

    adder = _create_adder()
    service_index = _create_service_index(service_resource)
    adder._NgwResourcesAdder__insertion_stack = [mock.Mock()]

    adder._NgwResourcesAdder__add_service(service_index)

    adder._NgwResourcesAdder__insert_group.assert_called_once_with(
        service_resource.display_name
    )
    adder._NgwResourcesAdder__add_service_layer.assert_has_calls(
        [
            mock.call(service_resource, first_layer),
            mock.call(service_resource, second_layer),
        ]
    )


def test_add_service_with_one_available_layer_does_not_create_group() -> None:
    skipped_layer = mock.Mock()
    added_layer = mock.Mock()
    service_resource = mock.Mock()
    service_resource.layers = [skipped_layer, added_layer]

    adder = _create_adder()
    adder._NgwResourcesAdder__skipped_resources = {id(skipped_layer)}
    service_index = _create_service_index(service_resource)

    adder._NgwResourcesAdder__add_service(service_index)

    adder._NgwResourcesAdder__insert_group.assert_not_called()
    adder._NgwResourcesAdder__add_service_layer.assert_called_once_with(
        service_resource, added_layer
    )
