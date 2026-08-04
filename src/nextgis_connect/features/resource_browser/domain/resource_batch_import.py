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
from enum import Enum, auto
from typing import Optional, Tuple


@dataclass(frozen=True)
class ResourceImportWarning:
    """Store a user-facing non-fatal batch import warning."""

    message: str
    detail: Optional[str] = None


class ResourceBatchImportStatus(Enum):
    """Identify the terminal state of a batch import operation."""

    SUCCEEDED = auto()
    CANCELLED = auto()
    FAILED = auto()


@dataclass(frozen=True)
class ResourceBatchImportResult:
    """Return the observable outcome of a batch import operation."""

    status: ResourceBatchImportStatus
    added_layer_ids: Tuple[str, ...] = ()
    warnings: Tuple[ResourceImportWarning, ...] = ()

    @property
    def is_success(self) -> bool:
        return self.status == ResourceBatchImportStatus.SUCCEEDED
