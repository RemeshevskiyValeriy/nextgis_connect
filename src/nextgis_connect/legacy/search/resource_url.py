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

from typing import List, Optional
from urllib.parse import urlparse

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)


class SearchResourceUrlParser:
    def resource_id(
        self,
        search_string: str,
        connection: NgwConnection,
    ) -> Optional[str]:
        parsed_url = urlparse(search_string.strip())
        if parsed_url.scheme == "" or parsed_url.netloc == "":
            return None

        if not self._is_same_web_gis(search_string, connection.url):
            return None

        path_parts = [
            path_part
            for path_part in parsed_url.path.split("/")
            if path_part != ""
        ]
        return self._resource_id_from_path(path_parts)

    def _resource_id_from_path(
        self,
        path_parts: List[str],
    ) -> Optional[str]:
        if len(path_parts) >= 2 and path_parts[0] == "resource":
            return self._normalized_resource_id(path_parts[1])

        if (
            len(path_parts) >= 3
            and path_parts[0] == "api"
            and path_parts[1] == "resource"
        ):
            return self._normalized_resource_id(path_parts[2])

        return None

    def _normalized_resource_id(self, value: str) -> Optional[str]:
        if not value.isnumeric():
            return None

        return str(int(value))

    def _is_same_web_gis(self, left_url: str, right_url: str) -> bool:
        return self._canonical_url(left_url) == self._canonical_url(right_url)

    def _canonical_url(self, url: str) -> str:
        parsed_url = urlparse(NgwConnection.normalize_url(url))
        scheme = parsed_url.scheme.lower()
        netloc = parsed_url.netloc.lower()

        return f"{scheme}://{netloc}"
