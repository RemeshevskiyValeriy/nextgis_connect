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

from typing import Any
from unittest.mock import MagicMock

from qgis.PyQt.QtCore import QObject


class MagicQObjectMock(QObject):
    _magic_mock: MagicMock

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._magic_mock = MagicMock()

    def __getattr__(self, name: str) -> Any:
        if hasattr(QObject, name):
            return getattr(super(), name)
        return getattr(self._magic_mock, name)
