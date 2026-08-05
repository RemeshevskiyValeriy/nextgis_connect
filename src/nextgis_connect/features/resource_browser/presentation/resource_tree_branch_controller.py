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

from typing import List, Tuple

from qgis.PyQt.QtCore import (
    QItemSelection,
    QModelIndex,
    QObject,
    QPersistentModelIndex,
    QTimer,
    pyqtSlot,
)
from qgis.PyQt.QtWidgets import QTreeView


class ResourceTreeBranchController(QObject):
    """Apply recursive tree operations to deduplicated selected branches."""

    def __init__(self, tree_view: QTreeView) -> None:
        super().__init__(tree_view)
        self._tree_view = tree_view
        self._expansion_roots: Tuple[QPersistentModelIndex, ...] = ()
        self._pending_fetches: List[QPersistentModelIndex] = []

        model = self._tree_view.model()
        if model is not None:
            model.rowsInserted.connect(self._on_rows_inserted)
            model.modelReset.connect(self._cancel_expansion)

        selection_model = self._tree_view.selectionModel()
        if selection_model is not None:
            selection_model.selectionChanged.connect(
                self._on_selection_changed
            )
        self._tree_view.collapsed.connect(self._on_branch_collapsed)

    @pyqtSlot()
    def expand_selected(self) -> None:
        """Expand every descendant of each selected branch root."""
        self._cancel_expansion()
        roots = self.selected_branch_roots()
        self._expansion_roots = tuple(
            QPersistentModelIndex(root) for root in roots
        )
        for root in roots:
            self._expand_branch(root)

    @pyqtSlot()
    def collapse_selected(self) -> None:
        """Collapse every loaded descendant of each selected branch root."""
        self._cancel_expansion()
        self._set_selected_branches_expanded(False)

    def selected_branch_roots(self) -> Tuple[QModelIndex, ...]:
        """Return unique selected indexes without nested branch roots."""
        selection_model = self._tree_view.selectionModel()
        if selection_model is None:
            return ()

        selected_indexes = selection_model.selectedRows(0)
        if len(selected_indexes) == 0:
            current_index = selection_model.currentIndex()
            if current_index.isValid():
                selected_indexes = [
                    current_index.sibling(current_index.row(), 0)
                ]

        roots: List[QModelIndex] = []
        for selected_index in selected_indexes:
            if not selected_index.isValid():
                continue

            index = selected_index.sibling(selected_index.row(), 0)
            if any(self._is_same_or_descendant(index, root) for root in roots):
                continue

            roots = [
                root
                for root in roots
                if not self._is_same_or_descendant(root, index)
            ]
            roots.append(index)

        return tuple(roots)

    def _set_selected_branches_expanded(self, expanded: bool) -> None:
        model = self._tree_view.model()
        if model is None:
            return

        pending_indexes = list(reversed(self.selected_branch_roots()))
        while len(pending_indexes) > 0:
            index = pending_indexes.pop()
            self._tree_view.setExpanded(index, expanded)

            for row in reversed(range(model.rowCount(index))):
                child_index = model.index(row, 0, index)
                if child_index.isValid():
                    pending_indexes.append(child_index)

    def _expand_branch(self, root: QModelIndex) -> None:
        model = self._tree_view.model()
        if model is None:
            return

        pending_indexes = [root]
        while len(pending_indexes) > 0:
            index = pending_indexes.pop()
            self._fetch_children(index)
            self._tree_view.setExpanded(index, True)

            for row in reversed(range(model.rowCount(index))):
                child_index = model.index(row, 0, index)
                if child_index.isValid():
                    pending_indexes.append(child_index)

    def _fetch_children(self, index: QModelIndex) -> None:
        model = self._tree_view.model()
        if model is None or not model.canFetchMore(index):
            return

        persistent_index = QPersistentModelIndex(index)
        if persistent_index not in self._pending_fetches:
            self._pending_fetches.append(persistent_index)
        model.fetchMore(index)

    @pyqtSlot(QModelIndex, int, int)
    def _on_rows_inserted(
        self,
        parent: QModelIndex,
        first_row: int,
        last_row: int,
    ) -> None:
        if not self._belongs_to_expansion(parent):
            return

        persistent_parent = QPersistentModelIndex(parent)
        self._pending_fetches = [
            pending_index
            for pending_index in self._pending_fetches
            if pending_index != persistent_parent
        ]

        model = self._tree_view.model()
        if model is None:
            return

        for row in range(first_row, last_row + 1):
            child_index = model.index(row, 0, parent)
            if child_index.isValid():
                self._expand_branch(child_index)

        QTimer.singleShot(0, self._finish_expansion_if_idle)

    @pyqtSlot(QModelIndex)
    def _on_branch_collapsed(self, index: QModelIndex) -> None:
        if self._belongs_to_expansion(index):
            self._cancel_expansion()

    @pyqtSlot(QItemSelection, QItemSelection)
    def _on_selection_changed(
        self,
        selected: QItemSelection,
        deselected: QItemSelection,
    ) -> None:
        del selected
        del deselected
        self._cancel_expansion()

    @pyqtSlot()
    def _finish_expansion_if_idle(self) -> None:
        if len(self._pending_fetches) == 0:
            self._expansion_roots = ()

    @pyqtSlot()
    def _cancel_expansion(self) -> None:
        self._expansion_roots = ()
        self._pending_fetches = []

    def _belongs_to_expansion(self, index: QModelIndex) -> bool:
        if not index.isValid():
            return False

        return any(
            root.isValid()
            and self._is_same_or_descendant(index, QModelIndex(root))
            for root in self._expansion_roots
        )

    def _is_same_or_descendant(
        self,
        index: QModelIndex,
        possible_ancestor: QModelIndex,
    ) -> bool:
        current_index = index
        while current_index.isValid():
            if current_index == possible_ancestor:
                return True
            current_index = current_index.parent()

        return False
