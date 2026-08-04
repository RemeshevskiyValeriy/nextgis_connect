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

import urllib.parse
from dataclasses import dataclass
from typing import Dict, Optional, Union


@dataclass(frozen=True)
class VectorLayerExportParams:
    format_name: str = "GPKG"
    fid_field: str = ""
    srs_id: Optional[int] = None
    has_geometry: bool = True
    zipped: bool = False

    def to_query(self) -> str:
        params: Dict[str, Union[int, str]] = {
            "format": self.format_name,
            "fid": self.fid_field,
            "zipped": str(self.zipped).lower(),
        }

        if self.has_geometry and self.srs_id is not None and self.srs_id > 0:
            params["srs"] = self.srs_id

        return urllib.parse.urlencode(params)
