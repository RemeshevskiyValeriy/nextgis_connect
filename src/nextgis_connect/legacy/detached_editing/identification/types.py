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

from enum import IntEnum
from typing import Tuple

from nextgis_connect.platform.qgis.compat import QgsFeatureId

LayerId = str
FeatureKey = Tuple[LayerId, QgsFeatureId]


class IdentificationTab(IntEnum):
    """Identification tabs for the feature identification results widget."""

    ATTRIBUTES = 0
    ATTACHMENTS = 1
    DESCRIPTION = 2


class AttachmentsSortMode(IntEnum):
    """Sorting modes for attachments."""

    BY_NAME = 0
    BY_TYPE = 1
    BY_SIZE = 2
