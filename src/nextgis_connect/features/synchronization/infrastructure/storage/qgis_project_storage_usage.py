from pathlib import Path
from typing import Iterable, Protocol, Set


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

            from nextgis_connect.legacy.detached_editing.utils import (
                container_path,
                is_ngw_container,
            )
        except Exception:
            return set()

        result: Set[Path] = set()
        for layer in QgsProject.instance().mapLayers().values():
            if not is_ngw_container(layer):
                continue
            try:
                result.add(container_path(layer))
            except Exception:
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
