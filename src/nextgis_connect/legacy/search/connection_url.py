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
from typing import Iterable, Optional
from urllib.parse import urlparse

from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)


@dataclass(frozen=True)
class SearchConnectionTarget:
    url: str
    connection: Optional[NgwConnection]

    @property
    def has_connection(self) -> bool:
        return self.connection is not None


class SearchConnectionTargetResolver:
    def resolve(
        self,
        search_string: str,
        current_connection: Optional[NgwConnection],
        connections: Iterable[NgwConnection],
    ) -> Optional[SearchConnectionTarget]:
        search_url = self._normalized_url(search_string)
        if search_url is None:
            return None

        if self._is_current_connection(search_url, current_connection):
            return None

        return SearchConnectionTarget(
            search_url,
            self._find_connection(search_url, connections),
        )

    def _normalized_url(self, value: str) -> Optional[str]:
        stripped_value = value.strip()
        if not self._looks_like_url(stripped_value):
            return None

        if "://" in stripped_value:
            normalized_value = stripped_value
        else:
            normalized_value = f"https://{stripped_value}"

        normalized_url = NgwConnection.normalize_url(normalized_value)
        parsed_url = urlparse(normalized_url)
        if parsed_url.scheme not in ("http", "https"):
            return None

        if parsed_url.netloc == "":
            return None

        return self._canonical_url(normalized_url)

    def _looks_like_url(self, value: str) -> bool:
        if value == "":
            return False

        if any(character.isspace() for character in value):
            return False

        if "://" in value:
            parsed_url = urlparse(value)
            return parsed_url.scheme in ("http", "https") and (
                parsed_url.netloc != ""
            )

        host = value.split("/", 1)[0].split(":", 1)[0].lower()
        return "." in host or host == "localhost"

    def _is_current_connection(
        self,
        url: str,
        current_connection: Optional[NgwConnection],
    ) -> bool:
        if current_connection is None:
            return False

        return self._is_same_web_gis(url, current_connection.url)

    def _find_connection(
        self,
        url: str,
        connections: Iterable[NgwConnection],
    ) -> Optional[NgwConnection]:
        for connection in connections:
            if self._is_same_web_gis(url, connection.url):
                return connection

        return None

    def _is_same_web_gis(self, left_url: str, right_url: str) -> bool:
        return self._canonical_url(left_url) == self._canonical_url(right_url)

    def _canonical_url(self, url: str) -> str:
        parsed_url = urlparse(NgwConnection.normalize_url(url))
        scheme = parsed_url.scheme.lower()
        netloc = parsed_url.netloc.lower()

        if not scheme or not netloc:
            return url.strip()

        return f"{scheme}://{netloc}"
