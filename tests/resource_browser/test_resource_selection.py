from typing import Dict, List
from unittest import mock

from nextgis_connect.features.resource_browser.infrastructure.resource_selection import (
    DemoProjectSelectionResolver,
)
from nextgis_connect.legacy.ngw.core import (
    NGWGroupResource,
    NGWResource,
    NGWWebMap,
)


class _ResourceIndex:
    def __init__(self, resource: NGWResource) -> None:
        self.resource = resource

    def data(self, role):
        del role
        return self.resource


class _ResourceTreeModel:
    def __init__(
        self,
        children: Dict[_ResourceIndex, List[_ResourceIndex]],
    ) -> None:
        self.children = children

    def rowCount(self, parent: _ResourceIndex) -> int:
        return len(self.children.get(parent, []))

    def index(
        self,
        row: int,
        column: int,
        parent: _ResourceIndex,
    ) -> _ResourceIndex:
        assert column == 0
        return self.children[parent][row]


def _resource_json(resource_id: int, resource_class: str):
    return {
        "resource": {
            "id": resource_id,
            "cls": resource_class,
            "display_name": f"Resource {resource_id}",
            "description": None,
            "parent": None,
            "owner_user": None,
            "children": True,
            "interfaces": [],
        }
    }


def _group(resource_id: int, resource_class: str) -> NGWGroupResource:
    return NGWGroupResource(
        mock.Mock(),
        _resource_json(resource_id, resource_class),
    )


def _webmap(resource_id: int) -> NGWWebMap:
    resource_json = _resource_json(resource_id, NGWWebMap.type_id)
    resource_json["webmap"] = {"root_item": {"children": []}}
    return NGWWebMap(mock.Mock(), resource_json)


def test_resolves_standalone_demo_project_to_nested_webmap() -> None:
    demo_index = _ResourceIndex(_group(1, "demo_project"))
    nested_group_index = _ResourceIndex(_group(2, "resource_group"))
    webmap_index = _ResourceIndex(_webmap(3))
    model = _ResourceTreeModel(
        {
            demo_index: [nested_group_index],
            nested_group_index: [webmap_index],
        }
    )

    resolution = DemoProjectSelectionResolver(model).resolve(
        [demo_index],
        True,
    )

    assert resolution.indices == (webmap_index,)
    assert resolution.allow_demo_project_resolution is False


def test_keeps_demo_project_as_group_when_webmap_is_absent() -> None:
    demo_index = _ResourceIndex(_group(1, "demo_project"))
    nested_group_index = _ResourceIndex(_group(2, "resource_group"))
    model = _ResourceTreeModel({demo_index: [nested_group_index]})

    resolution = DemoProjectSelectionResolver(model).resolve(
        [demo_index],
        True,
    )

    assert resolution.indices == (demo_index,)
    assert resolution.allow_demo_project_resolution is False


def test_uses_first_webmap_in_depth_first_model_order() -> None:
    demo_index = _ResourceIndex(_group(1, "demo_project"))
    group_index = _ResourceIndex(_group(2, "resource_group"))
    nested_webmap_index = _ResourceIndex(_webmap(3))
    root_webmap_index = _ResourceIndex(_webmap(4))
    model = _ResourceTreeModel(
        {
            demo_index: [group_index, root_webmap_index],
            group_index: [nested_webmap_index],
        }
    )

    resolution = DemoProjectSelectionResolver(model).resolve(
        [demo_index],
        True,
    )

    assert resolution.indices == (nested_webmap_index,)


def test_resolves_demo_project_in_combined_selection() -> None:
    demo_index = _ResourceIndex(_group(1, "demo_project"))
    other_index = _ResourceIndex(_group(2, "resource_group"))
    webmap_index = _ResourceIndex(_webmap(3))
    model = _ResourceTreeModel({demo_index: [webmap_index]})

    resolution = DemoProjectSelectionResolver(model).resolve(
        [demo_index, other_index],
        True,
    )

    assert resolution.indices == (webmap_index, other_index)
    assert resolution.allow_demo_project_resolution is False


def test_resolves_each_demo_project_in_multiple_selection() -> None:
    first_demo_index = _ResourceIndex(_group(1, "demo_project"))
    second_demo_index = _ResourceIndex(_group(2, "demo_project"))
    third_demo_index = _ResourceIndex(_group(3, "demo_project"))
    first_webmap_index = _ResourceIndex(_webmap(4))
    nested_group_index = _ResourceIndex(_group(5, "resource_group"))
    second_webmap_index = _ResourceIndex(_webmap(6))
    model = _ResourceTreeModel(
        {
            first_demo_index: [first_webmap_index],
            second_demo_index: [nested_group_index],
            nested_group_index: [second_webmap_index],
            third_demo_index: [],
        }
    )

    resolution = DemoProjectSelectionResolver(model).resolve(
        [first_demo_index, second_demo_index, third_demo_index],
        True,
    )

    assert resolution.indices == (
        first_webmap_index,
        second_webmap_index,
        third_demo_index,
    )
    assert resolution.allow_demo_project_resolution is False
