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
