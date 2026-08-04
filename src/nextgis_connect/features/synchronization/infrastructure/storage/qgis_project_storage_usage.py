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
from typing import Iterable, Protocol, Set

from nextgis_connect.legacy.detached_editing.utils import (
    ContainerError,
    container_path,
    is_ngw_container,
)


class ProjectStorageUsage(Protocol):
    """Inspect storage paths used by the current project."""

    def used_paths(self) -> Set[Path]:
        """Return storage paths used by the current project."""


class EmptyProjectStorageUsage:
    """Return no project storage usage."""

    def used_paths(self) -> Set[Path]:
        """Return an empty set of paths."""
        return set()


class QgisProjectStorageUsage:
    """Inspect detached storage usage in a QGIS project."""

    def used_paths(self) -> Set[Path]:
        """Return detached container paths used by the current QGIS project."""
        try:
            from qgis.core import QgsProject
        except ImportError:
            return set()

        result: Set[Path] = set()
        for layer in QgsProject.instance().mapLayers().values():
            if not is_ngw_container(layer):
                continue
            try:
                result.add(container_path(layer))
            except (ContainerError, TypeError):
                continue
        return result


def normalize_used_paths(paths: Iterable[Path]) -> Set[Path]:
    """Return resolved project usage paths."""
    result: Set[Path] = set()
    for path in paths:
        try:
            result.add(Path(path).resolve())
        except OSError:
            result.add(Path(path))
    return result
