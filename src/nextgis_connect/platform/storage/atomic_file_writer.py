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

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from nextgis_connect.platform.storage.errors import StorageError


@dataclass(frozen=True)
class AtomicWriteResult:
    """Describe an atomic file write result."""

    path: Path
    size_bytes: int
    sha256: str


class AtomicFileWriter:
    """Write files through a same-directory temporary file."""

    def write_bytes(
        self,
        target_path: Path,
        data: bytes,
        *,
        overwrite: bool = False,
    ) -> AtomicWriteResult:
        """Write bytes to a target path atomically."""
        target_path = Path(target_path)
        if target_path.exists() and not overwrite:
            raise StorageError(
                "Target file already exists",
                path=target_path,
                operation="write_bytes",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(target_path)
        try:
            with temp_path.open("wb") as file:
                file.write(data)
            os.replace(str(temp_path), str(target_path))
            return self._result(target_path)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def copy_from(
        self,
        source_path: Path,
        target_path: Path,
        *,
        overwrite: bool = False,
    ) -> AtomicWriteResult:
        """Copy a source file to a target path atomically."""
        source_path = Path(source_path)
        target_path = Path(target_path)
        if target_path.exists() and not overwrite:
            raise StorageError(
                "Target file already exists",
                path=target_path,
                operation="copy_from",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self._temporary_path(target_path)
        digest = hashlib.sha256()
        size_bytes = 0
        try:
            with source_path.open("rb") as source_file, temp_path.open(
                "wb"
            ) as target_file:
                while True:
                    chunk = source_file.read(1024 * 1024)
                    if not chunk:
                        break
                    target_file.write(chunk)
                    digest.update(chunk)
                    size_bytes += len(chunk)
            os.replace(str(temp_path), str(target_path))
            return AtomicWriteResult(
                path=target_path,
                size_bytes=size_bytes,
                sha256=digest.hexdigest(),
            )
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

    def _temporary_path(self, target_path: Path) -> Path:
        """Create a temporary path next to target."""
        descriptor, temp_file_name = tempfile.mkstemp(
            dir=str(target_path.parent),
            prefix=f".{target_path.name}.",
            suffix=".tmp",
        )
        os.close(descriptor)
        temp_path = Path(temp_file_name)
        temp_path.unlink(missing_ok=True)
        return temp_path

    def _result(self, target_path: Path) -> AtomicWriteResult:
        """Return file size and digest."""
        digest = hashlib.sha256()
        size_bytes = 0
        with target_path.open("rb") as file:
            while True:
                chunk = file.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size_bytes += len(chunk)
        return AtomicWriteResult(
            path=target_path,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
        )
