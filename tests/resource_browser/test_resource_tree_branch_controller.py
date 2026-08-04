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

from qgis.PyQt.QtCore import QItemSelectionModel, QModelIndex
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel
from qgis.PyQt.QtWidgets import QAbstractItemView, QTreeView

from nextgis_connect.features.resource_browser.presentation import (
    ResourceTreeBranchController,
)


class _LazyTreeModel(QStandardItemModel):
    def __init__(self) -> None:
        super().__init__()
        self._unloaded_children = {
            "Root": "Branch",
            "Branch": "Leaf",
        }
        self.appendRow(QStandardItem("Root"))

    def canFetchMore(self, parent: QModelIndex) -> bool:
        item = self.itemFromIndex(parent)
        return item is not None and item.text() in self._unloaded_children

    def fetchMore(self, parent: QModelIndex) -> None:
        item = self.itemFromIndex(parent)
        if item is None:
            return

        child_text = self._unloaded_children.pop(item.text(), None)
        if child_text is not None:
            item.appendRow(QStandardItem(child_text))


class TestResourceTreeBranchController:
    def test_expands_deduplicated_selected_branches(self, qgis_app) -> None:
        del qgis_app
        tree = self._create_tree()
        model = tree.model()
        assert isinstance(model, QStandardItemModel)
        controller = ResourceTreeBranchController(tree)

        first_root = model.index(0, 0)
        nested_branch = model.index(0, 0, first_root)
        second_root = model.index(1, 0)
        third_root = model.index(2, 0)
        self._select(tree, first_root, nested_branch, second_root)

        assert controller.selected_branch_roots() == (
            first_root,
            second_root,
        )

        controller.expand_selected()

        assert tree.isExpanded(first_root)
        assert tree.isExpanded(nested_branch)
        assert tree.isExpanded(second_root)
        assert not tree.isExpanded(third_root)

        tree.deleteLater()

    def test_expands_lazily_loaded_descendants_to_leaf(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        model = _LazyTreeModel()
        tree = QTreeView()
        tree.setModel(model)
        root = model.index(0, 0)
        tree.setCurrentIndex(root)
        controller = ResourceTreeBranchController(tree)

        controller.expand_selected()

        branch = model.index(0, 0, root)
        leaf = model.index(0, 0, branch)
        assert branch.isValid()
        assert leaf.isValid()
        assert tree.isExpanded(root)
        assert tree.isExpanded(branch)

        tree.deleteLater()

    def test_collapses_only_selected_branches_recursively(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        tree = self._create_tree()
        model = tree.model()
        assert isinstance(model, QStandardItemModel)
        controller = ResourceTreeBranchController(tree)

        first_root = model.index(0, 0)
        nested_branch = model.index(0, 0, first_root)
        second_root = model.index(1, 0)
        third_root = model.index(2, 0)
        tree.expandAll()
        self._select(tree, first_root, nested_branch, second_root)

        controller.collapse_selected()

        assert not tree.isExpanded(first_root)
        assert not tree.isExpanded(nested_branch)
        assert not tree.isExpanded(second_root)
        assert tree.isExpanded(third_root)

        tree.deleteLater()

    def _create_tree(self) -> QTreeView:
        model = QStandardItemModel()
        first_root = QStandardItem("First")
        first_branch = QStandardItem("First branch")
        first_branch.appendRow(QStandardItem("First leaf"))
        first_root.appendRow(first_branch)

        second_root = QStandardItem("Second")
        second_root.appendRow(QStandardItem("Second leaf"))

        third_root = QStandardItem("Third")
        third_root.appendRow(QStandardItem("Third leaf"))
        model.appendRow(first_root)
        model.appendRow(second_root)
        model.appendRow(third_root)

        tree = QTreeView()
        tree.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection
        )
        tree.setModel(model)
        return tree

    def _select(
        self,
        tree: QTreeView,
        *indexes: QModelIndex,
    ) -> None:
        selection_model = tree.selectionModel()
        assert selection_model is not None
        flags = (
            QItemSelectionModel.SelectionFlag.Select
            | QItemSelectionModel.SelectionFlag.Rows
        )
        for index in indexes:
            selection_model.select(index, flags)
