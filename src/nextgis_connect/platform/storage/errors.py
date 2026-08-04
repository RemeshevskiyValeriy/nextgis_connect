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


class StorageError(Exception):
    """Represent a technical storage layer error."""

    def __init__(self, message: str, **context: Any) -> None:
        """Initialize storage error context."""
        self.context = context
        details = self._format_context(context)
        if details:
            message = f"{message} ({details})"
        super().__init__(message)

    def _format_context(self, context: Dict[str, Any]) -> str:
        """Return context as a compact string."""
        return ", ".join(f"{key}={value}" for key, value in context.items())


class StorageIndexError(StorageError):
    """Represent a storage index failure."""


class StorageMigrationError(StorageError):
    """Represent a storage migration failure."""


class StoragePathError(StorageError):
    """Represent a storage path resolution failure."""


class StorageProtectionError(StorageError):
    """Represent a protected storage entry violation."""


class StorageLeaseError(StorageError):
    """Represent a storage lease failure."""


class StorageCleanupError(StorageError):
    """Represent a storage cleanup failure."""
