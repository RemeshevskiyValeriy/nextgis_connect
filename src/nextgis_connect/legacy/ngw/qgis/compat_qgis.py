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

from qgis import core
from qgis.PyQt import QtCore

COMPAT_PYQT_VERSION = QtCore.PYQT_VERSION_STR.split(".")


class CompatQt:
    @classmethod
    def has_redirect_policy(cls):
        pyqt_version = (
            int(COMPAT_PYQT_VERSION[0]),
            int(COMPAT_PYQT_VERSION[1]),
        )
        return pyqt_version >= (5, 9)

    @classmethod
    def get_clean_python_value(cls, v):
        if v == core.NULL:
            return None
        if isinstance(v, QtCore.QDateTime):
            return v.toPyDateTime()
        if isinstance(v, QtCore.QDate):
            return v.toPyDate()
        if isinstance(v, QtCore.QTime):
            return v.toPyTime()
        return v
