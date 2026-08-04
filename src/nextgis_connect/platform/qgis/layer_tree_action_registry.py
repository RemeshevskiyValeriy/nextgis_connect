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

from typing import Any, Callable, Dict, List, Optional

from qgis.gui import QgisInterface
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction, QMenu


class LayerTreeActionRegistry:
    """Own symmetric registration of actions in the QGIS layer tree."""

    def __init__(self, iface: QgisInterface) -> None:
        self._iface = iface
        self._actions: List[QAction] = []
        self._menu_icons: Dict[str, QIcon] = {}
        self._is_context_menu_hooked = False
        self._context_menu_signal: Optional[Any] = None
        self._context_menu_slot: Optional[Callable[[QMenu], None]] = None

    @property
    def registration_count(self) -> int:
        """Return the number of registrations currently owned."""
        return len(self._actions)

    def register(
        self,
        action: QAction,
        menu: str,
        layer_type: object,
        *,
        all_layers: bool,
        menu_icon: Optional[QIcon] = None,
    ) -> None:
        """Register an action and retain the matching removal record."""
        self._iface.addCustomActionForLayerType(
            action,
            menu,
            layer_type,
            allLayers=all_layers,
        )
        self._actions.append(action)
        if len(menu) > 0 and menu_icon is not None:
            self._menu_icons[menu] = menu_icon
            self._ensure_context_menu_hook()

    def clear(self) -> None:
        """Remove every registration exactly once, including duplicates."""
        actions = tuple(reversed(self._actions))
        self._actions.clear()
        first_error: Optional[Exception] = None
        for action in actions:
            try:
                self._iface.removeCustomActionForLayerType(action)
            except Exception as error:
                if first_error is None:
                    first_error = error

        self._clear_context_menu_hook()
        self._menu_icons.clear()

        if first_error is not None:
            raise first_error

    def _ensure_context_menu_hook(self) -> None:
        if self._is_context_menu_hooked:
            return

        layer_tree_view = self._iface.layerTreeView()
        if layer_tree_view is None:
            return

        context_menu_signal = getattr(
            layer_tree_view,
            "contextMenuAboutToShow",
            None,
        )
        if context_menu_signal is None:
            return

        self._context_menu_signal = context_menu_signal
        self._context_menu_slot = self._apply_menu_icons
        context_menu_signal.connect(self._context_menu_slot)
        self._is_context_menu_hooked = True

    def _clear_context_menu_hook(self) -> None:
        if not self._is_context_menu_hooked:
            return

        if (
            self._context_menu_signal is not None
            and self._context_menu_slot is not None
        ):
            try:
                self._context_menu_signal.disconnect(self._context_menu_slot)
            except (RuntimeError, TypeError):
                pass

        self._context_menu_signal = None
        self._context_menu_slot = None
        self._is_context_menu_hooked = False

    def _apply_menu_icons(self, menu: QMenu) -> None:
        for action in menu.actions():
            self._apply_action_menu_icon(action)
            child_menu = action.menu()
            if child_menu is not None:
                self._apply_menu_icons(child_menu)

    def _apply_action_menu_icon(self, action: QAction) -> None:
        icon = self._menu_icons.get(self._normalized_menu_text(action.text()))
        if icon is None:
            return

        action.setIcon(icon)
        action.setIconVisibleInMenu(True)

    def _normalized_menu_text(self, text: str) -> str:
        return text.replace("&", "")
