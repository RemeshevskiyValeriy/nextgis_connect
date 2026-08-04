import logging
import shutil
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

from qgis.core import QgsProject

from nextgis_connect.features.synchronization.infrastructure.storage.detached_storage_service import (
    DetachedStorageService,
)
from nextgis_connect.features.synchronization.infrastructure.storage.legacy_cache_migrator import (
    LegacyCacheMigrator,
)
from nextgis_connect.features.synchronization.infrastructure.storage.qgis_project_storage_usage import (
    QgisProjectStorageUsage,
)
from nextgis_connect.features.synchronization.infrastructure.storage.storage_cleanup_service import (
    StorageCleanupService,
)
from nextgis_connect.legacy.detached_editing.utils import (
    container_metadata,
    container_path,
    is_ngw_container,
    make_connection,
)
from nextgis_connect.legacy.ngw_connection.domain.connection import (
    NgwConnection,
)
from nextgis_connect.legacy.settings.ng_connect_settings import (
    NgConnectSettings,
)
from nextgis_connect.platform.storage.models import LayerKey
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.sqlite_storage_index import (
    SqliteStorageIndex,
)
from nextgis_connect.shared.constants import PLUGIN_NAME


@dataclass(frozen=True)
class _IndexedLayerContainer:
    """Represent a detached layer container stored in the cache index."""

    path: Path
    resource_id: int
    instance_uuid: str
    connection_id: Optional[str]
    has_local_changes: bool
    is_used_by_project: bool


@dataclass(frozen=True)
class _ProjectLayerContainer:
    """Represent a detached layer container currently used by the project."""

    path: Path
    label: str


class CacheMaintenanceService:
    """Maintain local detached cache lifecycle."""

    TEMPORARY_CACHE_MAX_AGE_SECONDS = 24 * 60 * 60
    TEMPORARY_FILE_PREFIX = "nextgis-connect-"
    TEMPORARY_DOWNLOAD_SUFFIX = ".download"

    __settings: NgConnectSettings
    __project_containers: Optional[List[_ProjectLayerContainer]]

    def __init__(self) -> None:
        self.__settings = NgConnectSettings()
        self.__project_containers = None
        Path(self.cache_directory).mkdir(parents=True, exist_ok=True)
        self.__storage_service = DetachedStorageService(
            Path(self.cache_directory)
        )

    @property
    def default_user_profile_cache_directory(self) -> str:
        return self.__settings.user_profile_cache_directory

    @property
    def cache_directory(self) -> str:
        return self.__settings.cache_directory

    @cache_directory.setter
    def cache_directory(self, value: Optional[str]) -> None:
        old_value = self.__settings.cache_directory
        self.__settings.cache_directory = value
        new_value = self.__settings.cache_directory
        if old_value == new_value:
            return

        old_cache_directory = Path(old_value)
        new_cache_directory = Path(new_value)
        shutil.copytree(
            old_cache_directory, new_cache_directory, dirs_exist_ok=True
        )
        shutil.rmtree(old_cache_directory)
        self.__storage_service = DetachedStorageService(new_cache_directory)

    @property
    def cache_duration(self) -> int:
        """Keeping cache duration in days"""
        return self.__settings.cache_duration

    @cache_duration.setter
    def cache_duration(self, value: int) -> None:
        self.__settings.cache_duration = value

    @property
    def cache_size(self) -> float:
        """Current cache size in KB"""
        return (
            StorageCleanupService(
                Path(self.cache_directory)
            ).cache_size_bytes()
            / 1024
        )

    @property
    def cache_max_size(self) -> int:
        """Cache max size in MB"""
        return self.__settings.cache_max_size

    @cache_max_size.setter
    def cache_max_size(self, value: int) -> None:
        self.__settings.cache_max_size = value

    @property
    def has_files_used_by_project(self) -> bool:
        return len(self.containers_used_by_project()) > 0

    @property
    def has_containers_with_changes(self) -> bool:
        return len(self.containers_with_changes()) > 0

    @property
    def need_migration(self) -> bool:
        old_plugin_cache_path = Path(
            self.__settings.old_plugin_cache_directory
        )
        custom_cache_path = Path(
            self.cache_directory,
        )
        for cache_path in (old_plugin_cache_path, custom_cache_path):
            if LegacyCacheMigrator(cache_path).need_migration():
                return True

        return False

    @property
    def can_migrate(self) -> bool:
        old_plugin_cache_path = Path(
            self.__settings.old_plugin_cache_directory
        )
        custom_cache_path = Path(
            self.cache_directory,
        )

        for cache_path in (old_plugin_cache_path, custom_cache_path):
            if not LegacyCacheMigrator(
                cache_path,
                QgisProjectStorageUsage(),
            ).can_migrate():
                return False

        return True

    def migrate(self, connections: List[NgwConnection]) -> bool:
        logger = logging.getLogger(PLUGIN_NAME)
        logger.debug("Start cache migration")

        old_plugin_cache_path = Path(
            self.__settings.old_plugin_cache_directory
        )

        # Migrate from default cache directory
        if not self.__migrate(
            old_plugin_cache_path, Path(self.cache_directory)
        ):
            return False

        if self.cache_directory != self.__settings.old_plugin_cache_directory:
            # Just update structure if custom cache directory was used
            if not self.__migrate(
                Path(self.cache_directory), Path(self.cache_directory)
            ):
                return False

        if self.cache_directory == self.__settings.old_plugin_cache_directory:
            # Reset if default value was stored in settings
            self.cache_directory = self.__settings.user_profile_cache_directory

        self.reassign_container_connection_ids(connections)

        logger.debug("Cache migration completed")

        return True

    def reassign_container_connection_ids(
        self,
        connections: List[NgwConnection],
    ) -> bool:
        connections_by_domain_uuid: Dict[str, List[NgwConnection]] = {}
        for connection in connections:
            connections_by_domain_uuid.setdefault(
                connection.domain_uuid,
                [],
            ).append(connection)

        for container_file in Path(self.cache_directory).glob("**/*.gpkg"):
            try:
                metadata = container_metadata(container_file)
            except Exception:
                continue

            domain_connections = connections_by_domain_uuid.get(
                metadata.instance_id,
                [],
            )
            if len(domain_connections) != 1:
                continue

            connection = domain_connections[0]
            container_file = self.__move_container_to_indexed_cache(
                container_file,
                metadata.resource_id,
                connection,
            )
            if container_file is None:
                return False

            if (
                metadata.connection_id == connection.id
                and metadata.instance_id == connection.domain_uuid
            ):
                continue

            if not self.__update_container_connection_metadata(
                container_file,
                connection,
            ):
                return False

        return True

    def __move_container_to_indexed_cache(
        self,
        container_file: Path,
        resource_id: int,
        connection: NgwConnection,
    ) -> Optional[Path]:
        return self.__storage_service.canonical_container_path(
            connection.domain_uuid,
            resource_id,
            connection_id=connection.id,
            source_container_path=container_file,
        )

    def __update_container_connection_metadata(
        self,
        container_file: Path,
        connection: NgwConnection,
    ) -> bool:
        try:
            with make_connection(container_file) as db_connection:
                cursor = db_connection.cursor()
                cursor.execute(
                    """
                    UPDATE ngw_metadata
                    SET connection_id = ?, instance_id = ?
                    """,
                    (connection.id, connection.domain_uuid),
                )
                db_connection.commit()
            metadata = container_metadata(container_file)
            is_registered = self.__storage_service.register_detached_container(
                connection.domain_uuid,
                metadata.resource_id,
                connection_id=connection.id,
                container_path=container_file,
                is_used_by_project=self.__is_project_container(container_file),
            )
            if not is_registered:
                raise RuntimeError(
                    "Could not register reassigned detached container"
                )
        except Exception:
            logger = logging.getLogger(PLUGIN_NAME)
            logger.exception(
                "Could not reassign detached container connection id"
            )
            return False

        return True

    def clear_cache(self) -> bool:
        logger = logging.getLogger(PLUGIN_NAME)

        self.__refresh_project_storage_usage_index()
        if self.has_files_used_by_project or self.has_containers_with_changes:
            logger.warning("Cache clearing was blocked by protected files")
            return False

        report = StorageCleanupService(
            Path(self.cache_directory)
        ).clear_disposable_cache(delete_referenced_attachments=True)
        if report.errors:
            logger.debug("Cache clearing error: %s", "; ".join(report.errors))
            return False

        return True

    def clear_connection_cache(self, connection) -> bool:
        self.__refresh_project_storage_usage_index()
        if len(self.containers_used_by_project(connection)) > 0:
            return False
        if len(self.containers_with_changes(connection)) > 0:
            return False

        logger = logging.getLogger(PLUGIN_NAME)
        cleanup_report = StorageCleanupService(
            Path(self.cache_directory)
        ).clear_connection_cache(connection.domain_uuid)
        if cleanup_report.errors or cleanup_report.blocked_files:
            logger.warning(
                "Could not clear indexed connection cache: %s",
                "; ".join(cleanup_report.errors + cleanup_report.warnings),
            )
            return False

        self.__remove_empty_dirs(self.cache_directory)
        return True

    def clear_resource_cache(
        self,
        connection: NgwConnection,
        resource_id: Union[int, str],
    ) -> bool:
        """Clear local cache for one resource in a connection."""
        resource_id_value = self.__parse_int(resource_id)
        if resource_id_value is None:
            return False

        self.__refresh_project_storage_usage_index()

        logger = logging.getLogger(PLUGIN_NAME)
        cleanup_report = StorageCleanupService(
            Path(self.cache_directory)
        ).clear_resource_cache(
            connection.domain_uuid,
            resource_id_value,
        )
        if cleanup_report.errors or cleanup_report.blocked_files:
            logger.warning(
                "Could not clear indexed resource cache: %s",
                "; ".join(cleanup_report.errors + cleanup_report.warnings),
            )
            return False

        self.__remove_empty_dirs(self.cache_directory)
        return True

    def containers_with_changes(
        self, connection=None
    ) -> List[Tuple[Path, str]]:
        return [
            (container.path, self.__indexed_container_label(container))
            for container in self.__indexed_layer_containers(
                connection,
                has_local_changes=True,
            )
        ]

    def containers_used_by_project(
        self, connection=None
    ) -> List[Tuple[Path, str]]:
        containers: List[Tuple[Path, str]] = []
        indexed_containers_by_path = self.__indexed_containers_by_path()
        for project_container in self.__project_layer_containers():
            file_path = project_container.path
            if not self.__is_cache_path(file_path):
                continue

            indexed_container = indexed_containers_by_path.get(
                self.__normalized_path(file_path)
            )
            if indexed_container is None:
                if not self.__is_legacy_project_container_for_connection(
                    file_path,
                    connection,
                ):
                    continue

            if (
                connection is not None
                and indexed_container is not None
                and not self.__is_indexed_container_for_connection(
                    indexed_container,
                    connection,
                )
            ):
                continue

            label = project_container.label
            if indexed_container is not None:
                label = self.__indexed_container_label(indexed_container)

            containers.append((file_path, label))

        return containers

    def purge_cache(self) -> bool:
        logger = logging.getLogger(PLUGIN_NAME)

        self.__clear_temporary_cache()

        need_check_size = self.cache_max_size != -1
        need_check_date = self.cache_duration != -1
        if not need_check_size and not need_check_date:
            logger.debug("Cache limits is disabled")
            return True

        self.__refresh_project_storage_usage_index()
        report = StorageCleanupService(
            Path(self.cache_directory)
        ).purge_automatic(
            max_size_bytes=None
            if not need_check_size
            else self.cache_max_size * 1024 * 1024,
            max_age_days=None if not need_check_date else self.cache_duration,
        )
        logger.debug(f"Deleted {report.deleted_files} indexed cache files")

        return not report.errors

    def __clear_temporary_cache(self) -> None:
        self.__clear_download_temporary_cache()
        self.__clear_system_temporary_cache()

    def __clear_download_temporary_cache(self) -> None:
        cache_path = Path(self.cache_directory)
        if not cache_path.exists():
            return

        for path in cache_path.glob(f"**/*{self.TEMPORARY_DOWNLOAD_SUFFIX}"):
            self.__unlink_stale_temporary_path(path)

    def __clear_system_temporary_cache(self) -> None:
        temporary_root = Path(tempfile.gettempdir())
        if not temporary_root.exists():
            return

        for path in temporary_root.glob(f"{self.TEMPORARY_FILE_PREFIX}*"):
            self.__unlink_stale_temporary_path(path)

    def __unlink_stale_temporary_path(self, path: Path) -> None:
        try:
            age_seconds = time.time() - path.stat().st_mtime
        except OSError:
            return

        if age_seconds < self.TEMPORARY_CACHE_MAX_AGE_SECONDS:
            return

        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except OSError:
            logging.getLogger(PLUGIN_NAME).debug(
                "Could not remove temporary cache path: %s",
                path,
                exc_info=True,
            )

    def __remove_empty_dirs(self, path: Union[str, Path]):
        path = Path(path)

        for sub_path in path.iterdir():
            if not sub_path.is_dir():
                continue
            self.__remove_empty_dirs(sub_path)

        if path == Path(self.cache_directory):
            return

        if not any(path.iterdir()):
            path.rmdir()

    def __indexed_layer_containers(
        self,
        connection: Optional[NgwConnection] = None,
        *,
        has_local_changes: Optional[bool] = None,
        is_used_by_project: Optional[bool] = None,
    ) -> List[_IndexedLayerContainer]:
        path_resolver = StoragePathResolver(Path(self.cache_directory))
        containers: List[_IndexedLayerContainer] = []
        for layer_entry in self.__storage_index().layer_entries(
            has_local_changes=has_local_changes,
            is_used_by_project=is_used_by_project,
        ):
            container = self.__indexed_layer_container(
                layer_entry,
                path_resolver,
            )
            if container is None:
                continue
            if (
                connection is not None
                and not self.__is_indexed_container_for_connection(
                    container,
                    connection,
                )
            ):
                continue
            containers.append(container)

        return containers

    def __indexed_layer_container(
        self,
        layer_entry: Dict[str, object],
        path_resolver: StoragePathResolver,
    ) -> Optional[_IndexedLayerContainer]:
        relative_path = layer_entry.get("relative_path")
        if relative_path is None:
            return None

        instance_uuid = str(layer_entry["instance_uuid"])
        path = path_resolver.absolute_from_entry(
            Path(str(relative_path)),
        )
        connection_id = layer_entry["connection_id"]
        return _IndexedLayerContainer(
            path=path,
            resource_id=int(layer_entry["resource_id"]),
            instance_uuid=instance_uuid,
            connection_id=None
            if connection_id is None
            else str(connection_id),
            has_local_changes=bool(layer_entry["has_local_changes"]),
            is_used_by_project=bool(layer_entry["is_used_by_project"]),
        )

    def __indexed_containers_by_path(
        self,
    ) -> Dict[Path, _IndexedLayerContainer]:
        return {
            self.__normalized_path(container.path): container
            for container in self.__indexed_layer_containers()
        }

    def __storage_index(self) -> SqliteStorageIndex:
        path_resolver = StoragePathResolver(Path(self.cache_directory))
        return SqliteStorageIndex(path_resolver.index_path())

    def __refresh_project_storage_usage_index(self) -> None:
        project_paths = {
            self.__normalized_path(project_container.path)
            for project_container in self.__project_layer_containers()
            if self.__is_cache_path(project_container.path)
        }
        for container in self.__indexed_layer_containers():
            is_used_by_project = (
                self.__normalized_path(container.path) in project_paths
            )
            if container.is_used_by_project == is_used_by_project:
                continue

            self.__storage_service.detached_layers.mark_used_by_project(
                LayerKey(container.instance_uuid, container.resource_id),
                is_used_by_project,
            )

    def __indexed_container_label(
        self,
        container: _IndexedLayerContainer,
    ) -> str:
        try:
            metadata = container_metadata(container.path)
        except Exception:
            return f"Resource id={container.resource_id}"

        return f"{metadata.layer_name} (id={metadata.resource_id})"

    def __is_container_for_connection(self, metadata, connection) -> bool:
        connection_ids = {
            connection_id
            for connection_id in (
                connection.id,
                *connection.old_connection_ids,
            )
            if connection_id
        }
        return (
            metadata.connection_id in connection_ids
            or metadata.instance_id == connection.domain_uuid
        )

    def __is_indexed_container_for_connection(
        self,
        container: _IndexedLayerContainer,
        connection: NgwConnection,
    ) -> bool:
        connection_ids = {
            connection_id
            for connection_id in (
                connection.id,
                *connection.old_connection_ids,
            )
            if connection_id
        }
        return (
            container.instance_uuid == connection.domain_uuid
            or container.connection_id in connection_ids
        )

    def __is_legacy_project_container_for_connection(
        self,
        file_path: Path,
        connection: Optional[NgwConnection],
    ) -> bool:
        if connection is None:
            return True

        try:
            metadata = container_metadata(file_path)
        except Exception:
            return False

        return self.__is_container_for_connection(metadata, connection)

    def __project_layer_containers(self) -> List[_ProjectLayerContainer]:
        if self.__project_containers is None:
            self.__project_containers = [
                _ProjectLayerContainer(container_path(layer), layer.name())
                for layer in QgsProject().instance().mapLayers().values()
                if is_ngw_container(layer)
            ]

        return self.__project_containers

    def __normalized_path(self, path: Path) -> Path:
        try:
            return path.resolve()
        except OSError:
            return path

    def __is_project_container(self, path: Path) -> bool:
        """Return whether the current project uses a container path."""
        normalized_path = self.__normalized_path(path)
        return any(
            self.__normalized_path(container.path) == normalized_path
            for container in self.__project_layer_containers()
        )

    def __is_cache_path(self, file_path: Path) -> bool:
        try:
            file_path.resolve().relative_to(
                Path(self.cache_directory).resolve()
            )
        except ValueError:
            return False

        return True

    def __migrate(self, old_base: Path, new_base: Path) -> bool:
        if not old_base.exists():
            return True

        try:
            report = LegacyCacheMigrator(
                old_base,
                QgisProjectStorageUsage(),
                target_cache_root=new_base,
            ).migrate()
        except Exception:
            logging.getLogger(PLUGIN_NAME).exception(
                "Could not migrate legacy cache"
            )
            return False

        if old_base != new_base and old_base.exists():
            try:
                old_base.rmdir()
            except OSError:
                pass

        return len(report.errors) == 0

    def __parse_int(self, value: object) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
