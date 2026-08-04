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

from typing import Any, Dict

from .ngw_resource import NGWResource, dict_to_object


class NGWWfsConnection(NGWResource):
    type_id = "wfsclient_connection"

    def _construct(self):
        super()._construct()
        self.wfs = dict_to_object(self._json[self.type_id])

    @property
    def connection_info(self) -> Dict[str, Any]:
        return self._json[self.type_id]
