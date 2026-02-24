from dataclasses import dataclass
from typing import Any, Optional
from unittest.mock import MagicMock, call

from nextgis_connect.ngw.core.ngw_resource import (
    NGWResource,
    NGWResourceDeleteSummary,
)


@dataclass(frozen=True)
class _ParentResource:
    id: int
    parent: Optional[Any] = None


@dataclass(frozen=True)
class _ResourceCommon:
    parent: Optional[Any]


@dataclass(frozen=True)
class _ResourceFactory:
    connection: MagicMock


@dataclass(frozen=True)
class _Resource:
    resource_id: int
    res_factory: _ResourceFactory
    common: _ResourceCommon


class TestNGWResourceBatchDelete:
    def test_delete_resources_removes_child_when_parent_selected(
        self,
    ) -> None:
        connection = MagicMock()
        parent_resource = self._resource(10, 0, connection)
        child_resource = self._resource(11, 10, connection)

        deleted_resources = NGWResource.delete_resources(
            [child_resource, parent_resource]
        )

        assert deleted_resources == [parent_resource]
        connection.post.assert_called_once_with(
            "/api/resource/delete?resources=10&partial=true",
            params={"resources": "10", "partial": "true"},
        )

    def test_delete_resources_removes_descendant_when_ancestor_selected(
        self,
    ) -> None:
        connection = MagicMock()
        ancestor_resource = self._resource(10, 0, connection)
        parent_resource = self._parent(20, self._parent(10))
        descendant_resource = self._resource(
            30, 20, connection, parent_resource
        )

        deleted_resources = NGWResource.delete_resources(
            [descendant_resource, ancestor_resource]
        )

        assert deleted_resources == [ancestor_resource]
        connection.post.assert_called_once_with(
            "/api/resource/delete?resources=10&partial=true",
            params={"resources": "10", "partial": "true"},
        )

    def test_delete_resources_keeps_independent_resources(self) -> None:
        connection = MagicMock()
        first_resource = self._resource(10, 0, connection)
        second_resource = self._resource(20, 0, connection)

        deleted_resources = NGWResource.delete_resources(
            [first_resource, second_resource]
        )

        assert deleted_resources == [first_resource, second_resource]
        connection.post.assert_called_once_with(
            "/api/resource/delete?resources=10,20&partial=true",
            params={"resources": "10,20", "partial": "true"},
        )

    def test_delete_resources_ignores_root_resource(self) -> None:
        connection = MagicMock()
        root_resource = self._resource(0, 0, connection)
        child_resource = self._resource(10, 0, connection)

        deleted_resources = NGWResource.delete_resources(
            [root_resource, child_resource]
        )

        assert deleted_resources == [child_resource]
        connection.post.assert_called_once_with(
            "/api/resource/delete?resources=10&partial=true",
            params={"resources": "10", "partial": "true"},
        )

    def test_simulate_delete_resources_removes_child_when_parent_selected(
        self,
    ) -> None:
        connection = MagicMock()
        connection.get.side_effect = [
            {
                "affected": {
                    "count": 11,
                    "resources": {
                        "resource_group": 1,
                        "vector_layer": 4,
                        "qgis_vector_style": 4,
                        "basemap_layer": 1,
                        "webmap": 1,
                    },
                },
                "unaffected": {
                    "count": 0,
                    "resources": {},
                },
            },
            {
                "affected": {
                    "resource_group": {
                        "label": "Resource group",
                    },
                    "vector_layer": {
                        "label": "Vector layer",
                    },
                },
            },
        ]
        parent_resource = self._resource(10, 0, connection)
        child_resource = self._resource(11, 10, connection)

        preview = NGWResource.simulate_delete_resources(
            [child_resource, parent_resource]
        )

        assert preview.affected.count == 11
        assert preview.affected.resources == {
            "resource_group": 1,
            "vector_layer": 4,
            "qgis_vector_style": 4,
            "basemap_layer": 1,
            "webmap": 1,
        }
        assert preview.unaffected.count == 0
        assert preview.unaffected.resources == {}
        assert preview.resource_labels == {
            "resource_group": "Resource group",
            "vector_layer": "Vector layer",
        }
        connection.get.assert_has_calls(
            [
                call("/api/resource/delete?resources=10", feedback=None),
                call(
                    "/api/component/resource/blueprint",
                    feedback=None,
                ),
            ]
        )

    def test_simulate_delete_resources_ignores_root_resource(self) -> None:
        connection = MagicMock()
        root_resource = self._resource(0, 0, connection)

        preview = NGWResource.simulate_delete_resources([root_resource])

        assert preview.affected.count == 0
        assert preview.affected.resources == {}
        assert preview.unaffected.count == 0
        assert preview.unaffected.resources == {}
        connection.get.assert_not_called()

    def test_delete_summary_uses_resources_as_count_fallback(self) -> None:
        summary = NGWResourceDeleteSummary.from_json(
            {
                "resources": {
                    "resource_group": 1,
                    "vector_layer": 2,
                },
            }
        )

        assert summary.count == 3
        assert summary.resources == {
            "resource_group": 1,
            "vector_layer": 2,
        }

    @staticmethod
    def _resource(
        resource_id: int,
        parent_id: int,
        connection: MagicMock,
        parent: Optional[Any] = None,
    ) -> _Resource:
        if parent is None:
            parent = TestNGWResourceBatchDelete._parent(parent_id)

        resource_factory = _ResourceFactory(connection=connection)
        common = _ResourceCommon(parent=parent)

        return _Resource(
            resource_id=resource_id,
            res_factory=resource_factory,
            common=common,
        )

    @staticmethod
    def _parent(
        parent_id: int, parent: Optional[Any] = None
    ) -> _ParentResource:
        return _ParentResource(id=parent_id, parent=parent)
