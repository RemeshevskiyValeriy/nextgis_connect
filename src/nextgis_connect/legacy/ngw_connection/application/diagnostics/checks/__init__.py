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

from typing import List

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)

from .base import BaseConnectionCheck


def build_connection_checks(
    connection: NgwConnection,
) -> List[BaseConnectionCheck]:
    from .certificate import CertificateCheck
    from .current_user import CurrentUserCheck
    from .download import DownloadCheck
    from .plugin_version import PluginVersionCheck
    from .root_resource import RootResourceAccessCheck
    from .server_version import ServerVersionCheck
    from .upload import UploadCheck

    return [
        PluginVersionCheck(connection),
        ServerVersionCheck(connection),
        CertificateCheck(connection),
        RootResourceAccessCheck(connection),
        CurrentUserCheck(connection),
        DownloadCheck(connection),
        UploadCheck(connection),
    ]
