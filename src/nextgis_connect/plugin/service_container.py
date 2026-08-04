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
