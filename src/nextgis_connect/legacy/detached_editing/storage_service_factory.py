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

from pathlib import Path

from nextgis_connect.features.synchronization.infrastructure.storage import (
    DetachedStorageService,
)
from nextgis_connect.legacy.settings import NgConnectSettings


class DetachedStorageServiceFactory:
    """Create detached storage services for the current settings."""

    @classmethod
    def create(cls) -> DetachedStorageService:
        """Return a detached storage service bound to the configured cache."""
        return DetachedStorageService(
            Path(NgConnectSettings().cache_directory)
        )
