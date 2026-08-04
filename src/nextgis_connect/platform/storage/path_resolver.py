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

from pathlib import Path, PurePath

from nextgis_connect.platform.storage.errors import StoragePathError
from nextgis_connect.platform.storage.models import StorageKey


class StoragePathResolver:
    """Resolve stable cache paths for storage keys."""

    DIGEST_DIRECTORY_LENGTH = 32
    LEGACY_DIGEST_DIRECTORY_LENGTHS = (64,)

    def __init__(self, cache_root: Path) -> None:
        """Initialize resolver for a cache root."""
        self._cache_root = Path(cache_root)

    @property
    def cache_root(self) -> Path:
        """Return the cache root path."""
        return self._cache_root

    def index_path(self) -> Path:
        """Return the global SQLite index path."""
        return self._cache_root / "storage.sqlite"

    def resolve(
        self,
        storage_key: StorageKey,
        file_name: str,
        *,
        create_parent: bool = False,
    ) -> Path:
        """Return an absolute path for a storage key."""
        self._validate_file_name(file_name)
        digest = storage_key.digest[: self.DIGEST_DIRECTORY_LENGTH]
        absolute_path = self._cache_root / digest[:2] / digest / file_name
        if create_parent:
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return absolute_path

    def relative_to_cache(self, path: Path) -> Path:
        """Return a path relative to the global cache root."""
        absolute_path = Path(path).resolve()
        cache_root = self._cache_root.resolve()
        try:
            return absolute_path.relative_to(cache_root)
        except ValueError as error:
            raise StoragePathError(
                "Path is outside storage root",
                path=path,
            ) from error

    def absolute_from_entry(
        self,
        relative_path: Path,
    ) -> Path:
        """Return an absolute path from an indexed relative path."""
        cache_root = self._cache_root.resolve()
        absolute_path = (cache_root / relative_path).resolve()
        try:
            absolute_path.relative_to(cache_root)
        except ValueError as error:
            raise StoragePathError(
                "Indexed path is outside storage root",
                path=relative_path,
            ) from error
        return absolute_path

    @classmethod
    def is_indexed_storage_path(
        cls,
        path: PurePath,
        *,
        include_legacy: bool = True,
    ) -> bool:
        """Return whether a path has a supported indexed hash layout."""
        if len(path.parts) < 3:
            return False

        prefix = path.parts[-3]
        digest = path.parts[-2]
        supported_lengths = {cls.DIGEST_DIRECTORY_LENGTH}
        if include_legacy:
            supported_lengths.update(cls.LEGACY_DIGEST_DIRECTORY_LENGTHS)

        if len(prefix) != 2 or len(digest) not in supported_lengths:
            return False
        if digest[:2] != prefix:
            return False

        return all(
            character in "0123456789abcdefABCDEF" for character in digest
        )

    def _validate_file_name(self, file_name: str) -> None:
        """Validate a stable storage file name."""
        if not file_name:
            raise StoragePathError("Storage file name is empty")

        path = Path(file_name)
        if path.name != file_name:
            raise StoragePathError(
                "Storage file name must not contain path separators",
                file_name=file_name,
            )
