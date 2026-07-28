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
