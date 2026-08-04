from typing import List, Optional

from qgis.gui import QgisInterface
from qgis.PyQt.QtWidgets import QAction


class LayerTreeActionRegistry:
    """Own symmetric registration of actions in the QGIS layer tree."""

    def __init__(self, iface: QgisInterface) -> None:
        self._iface = iface
        self._actions: List[QAction] = []

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
    ) -> None:
        """Register an action and retain the matching removal record."""
        self._iface.addCustomActionForLayerType(
            action,
            menu,
            layer_type,
            allLayers=all_layers,
        )
        self._actions.append(action)

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

        if first_error is not None:
            raise first_error
