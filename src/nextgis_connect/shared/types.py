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

from typing import TypeVar, Union

from nextgis_connect.platform.qgis.compat import QgsFeatureId

FeatureId = QgsFeatureId
FieldId = int
AttachmentId = int

NgwFeatureId = int
NgwFieldId = int
NgwAttachmentId = int

VersionId = int

FileObjectId = int

WktString = str
Wkb64String = str


class UnsetType:
    """Represent an unset value.

    Distinguish an explicitly unset value from ``None`` in typed data
    structures.
    """

    def __repr__(self) -> str:
        """Return the debug representation.

        :return: Debug representation.
        """
        return "<UNSET>"

    def __bool__(self):
        """Return the boolean value.

        :return: Always ``False``.
        """
        return False


Unset = UnsetType()

T = TypeVar("T")
Unsettable = Union[T, UnsetType]
