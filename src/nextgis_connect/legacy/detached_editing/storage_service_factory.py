from pathlib import Path

from nextgis_connect.features.synchronization.infrastructure.storage import (
    DetachedStorageService,
)
from nextgis_connect.legacy.settings import NgConnectSettings


class DetachedStorageServiceFactory:
    """Create detached storage services for the current settings."""

    @classmethod
    def create(cls) -> DetachedStorageService:
        """Return a detached storage service bound to the configured cache."""
        return DetachedStorageService(
            Path(NgConnectSettings().cache_directory)
        )
