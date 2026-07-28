from pathlib import Path

from nextgis_connect.platform.storage.errors import StoragePathError
from nextgis_connect.platform.storage.models import StorageKey


class StoragePathResolver:
    """Resolve stable cache paths for storage keys."""

    def __init__(self, cache_root: Path) -> None:
        """Initialize resolver for a cache root."""
        self._cache_root = Path(cache_root)

    @property
    def cache_root(self) -> Path:
        """Return the cache root path."""
        return self._cache_root

    def instance_root(self, instance_uuid: str) -> Path:
        """Return the root directory for an instance."""
        return self._cache_root / instance_uuid

    def index_path(self, instance_uuid: str) -> Path:
        """Return the SQLite index path for an instance."""
        return self.instance_root(instance_uuid) / "storage.sqlite"

    def resolve(
        self,
        storage_key: StorageKey,
        file_name: str,
        *,
        create_parent: bool = False,
    ) -> Path:
        """Return an absolute path for a storage key."""
        self._validate_file_name(file_name)
        digest = storage_key.digest
        absolute_path = (
            self.instance_root(storage_key.instance_uuid)
            / digest[:2]
            / digest
            / file_name
        )
        if create_parent:
            absolute_path.parent.mkdir(parents=True, exist_ok=True)
        return absolute_path

    def relative_to_instance(self, path: Path, instance_uuid: str) -> Path:
        """Return an instance-relative path."""
        absolute_path = Path(path).resolve()
        instance_root = self.instance_root(instance_uuid).resolve()
        try:
            return absolute_path.relative_to(instance_root)
        except ValueError as error:
            raise StoragePathError(
                "Path is outside instance storage root",
                instance_uuid=instance_uuid,
                path=path,
            ) from error

    def absolute_from_entry(
        self,
        instance_uuid: str,
        relative_path: Path,
    ) -> Path:
        """Return an absolute path from an indexed relative path."""
        return self.instance_root(instance_uuid) / relative_path

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
