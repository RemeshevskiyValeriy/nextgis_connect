from dataclasses import dataclass
from typing import Optional

from qgis.core import QgsTaskManager

from nextgis_connect.legacy.detached_editing.detached_editing import (
    DetachedEditing,
)
from nextgis_connect.legacy.notifier.notifier_interface import (
    NotifierInterface,
)


@dataclass
class ServiceContainer:
    """Store plugin runtime services.

    Carry optional service references while the plugin container wires
    lifecycle dependencies.

    :ivar notifier: Plugin notifier service.
    :ivar task_manager: Plugin task manager service.
    :ivar detached_editing: Detached editing service.
    """

    notifier: Optional[NotifierInterface] = None
    task_manager: Optional[QgsTaskManager] = None
    detached_editing: Optional[DetachedEditing] = None
