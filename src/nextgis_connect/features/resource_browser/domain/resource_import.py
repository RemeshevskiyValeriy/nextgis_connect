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

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional, Tuple


class ResourceImportMode(Enum):
    """Identify direct QGIS layer representations of a Web GIS resource."""

    MVT = auto()
    TMS = auto()
    EXPERIMENTAL_NGW = auto()


@dataclass(frozen=True)
class ResourceImportSource:
    """Describe a Web GIS resource without depending on an SDK model."""

    connection_url: str
    connection_id: str
    connection_instance_id: str
    resource_id: int
    display_name: str
    auth_config_id: Optional[str] = None
    provider_connection_url: Optional[str] = field(
        default=None,
        repr=False,
    )


@dataclass(frozen=True)
class ResourceImportStyle:
    """Describe one QGIS style without depending on an SDK resource."""

    name: str
    qml: str


@dataclass(frozen=True)
class ResourceImportExtent:
    """Describe a source extent without depending on QGIS types."""

    x_min: float
    y_min: float
    x_max: float
    y_max: float
    coordinate_reference_system_auth_id: str = "EPSG:4326"


@dataclass(frozen=True)
class ResourceImportRequest:
    """Describe one direct layer import operation."""

    mode: ResourceImportMode
    source: ResourceImportSource
    render_resource_id: Optional[int] = None
    no_data_response_code: int = 204
    render_resource_ids: Tuple[int, ...] = ()
    styles: Tuple[ResourceImportStyle, ...] = ()
    default_style_name: Optional[str] = None
    source_extent: Optional[ResourceImportExtent] = None
