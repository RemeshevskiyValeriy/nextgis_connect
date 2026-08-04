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

from typing import Any, Dict, List, Set


class ResourceOwnerSuggestionParser:
    """Extract owner names from NGW user payloads.

    Convert user records into unique owner names suitable for search
    suggestions while skipping system users.
    """

    def parse(self, users: Any) -> List[str]:
        """Parse owner names from user records.

        :param users: NGW user records payload.
        :return: Sorted owner names.
        """
        if not isinstance(users, list):
            return []

        owner_names: Set[str] = set()
        for user in users:
            if not isinstance(user, dict):
                continue

            if user.get("system") is True:
                continue

            owner_name = self._owner_name(user)
            if owner_name == "":
                continue

            owner_names.add(owner_name)

        return sorted(owner_names, key=str.casefold)

    def _owner_name(self, user: Dict[str, Any]) -> str:
        display_name = user.get("display_name")
        if isinstance(display_name, str) and display_name.strip() != "":
            return display_name.strip()

        keyname = user.get("keyname")
        if isinstance(keyname, str) and keyname.strip() != "":
            return keyname.strip()

        return ""
