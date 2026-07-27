from dataclasses import dataclass
from typing import Optional

from qgis.core import QgsTaskManager

from nextgis_connect.detached_editing.detached_editing import DetachedEditing
from nextgis_connect.notifier.notifier_interface import NotifierInterface


@dataclass
class ServiceContainer:
    notifier: Optional[NotifierInterface] = None
    task_manager: Optional[QgsTaskManager] = None
    detached_editing: Optional[DetachedEditing] = None
