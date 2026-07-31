import logging
import re
import shutil
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
from nextgis_connect.shared.constants import PLUGIN_NAME


class CacheMaintenanceService:
    """Maintain local detached cache lifecycle."""

    __settings: NgConnectSettings
    __project_containers: Optional[List[Path]]
    __uuid_pattern = re.compile(
        r"^[a-f0-9]{8}-[a-f0-9]{4}-[1-5][a-f0-9]{3}-"
        r"[89ab][a-f0-9]{3}-[a-f0-9]{12}$",
        re.IGNORECASE,
    )

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
        cache_path = Path(self.cache_directory)
        cache_size = 0.0
        for file_path in cache_path.glob("**/*"):
            if not file_path.is_file():
                continue
            if self.__is_storage_metadata_file(file_path):
                continue
            cache_size += file_path.stat().st_size / 1024
        return cache_size

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

            for directory in cache_path.glob("*"):
                if not self.__is_uuid(directory.name):
                    continue

                if any(True for _ in directory.glob("*.gpkg")):
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

            for directory in cache_path.glob("*"):
                if not self.__is_uuid(directory.name):
                    continue

                gpkg_files = list(directory.glob("*.gpkg"))
                for gpkg_file in gpkg_files:
                    if self.__is_file_used_by_project(gpkg_file):
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
            container_file = self.__move_container_to_connection_cache(
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

    def __move_container_to_connection_cache(
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

    def __move_detached_container_service_files(
        self,
        old_container_file: Path,
        new_container_file: Path,
    ) -> None:
        for service_file in old_container_file.parent.glob(
            f"{old_container_file.name}-*"
        ):
            suffix = service_file.name[len(old_container_file.name) :]
            target_file = new_container_file.parent / (
                new_container_file.name + suffix
            )
            if target_file.exists():
                continue
            service_file.replace(target_file)

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
        except Exception:
            logger = logging.getLogger(PLUGIN_NAME)
            logger.exception(
                "Could not reassign detached container connection id"
            )
            return False

        return True

    def clear_cache(self) -> bool:
        logger = logging.getLogger(PLUGIN_NAME)

        self.__refresh_detached_storage_index()
        if self.has_files_used_by_project or self.has_containers_with_changes:
            logger.warning("Cache clearing was blocked by protected files")
            return False

        report = StorageCleanupService(
            Path(self.cache_directory)
        ).clear_disposable_cache()
        if report.errors:
            logger.debug("Cache clearing error: %s", "; ".join(report.errors))
            return False

        return True

    def clear_connection_cache(self, connection) -> bool:
        self.__refresh_detached_storage_index()
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

        has_errors = False
        cache_paths = self.__connection_cache_paths(connection)

        for cache_path in sorted(
            cache_paths, key=lambda path: len(path.parts), reverse=True
        ):
            if not cache_path.exists():
                continue

            try:
                if cache_path.is_dir():
                    try:
                        cache_path.rmdir()
                    except OSError:
                        continue
                else:
                    cache_path.unlink()
            except Exception:
                logger.exception(f"Could not delete cache path {cache_path}")
                has_errors = True

        self.__remove_empty_dirs(self.cache_directory)
        return not has_errors

    def containers_with_changes(
        self, connection=None
    ) -> List[Tuple[Path, str]]:
        containers: List[Tuple[Path, str]] = []
        for file_path in Path(self.cache_directory).glob("**/*.gpkg"):
            try:
                metadata = container_metadata(file_path)
            except Exception:
                continue

            if not metadata.has_changes:
                continue

            if (
                connection is not None
                and not self.__is_container_for_connection(
                    metadata,
                    connection,
                )
            ):
                continue

            containers.append(
                (
                    file_path,
                    f"{metadata.layer_name} (id={metadata.resource_id})",
                )
            )

        return containers

    def containers_used_by_project(
        self, connection=None
    ) -> List[Tuple[Path, str]]:
        containers: List[Tuple[Path, str]] = []
        for file_path in self.__project_container_paths():
            if not self.__is_cache_path(file_path):
                continue

            try:
                metadata = container_metadata(file_path)
            except Exception:
                if connection is not None:
                    continue

                containers.append((file_path, file_path.name))
                continue

            if (
                connection is not None
                and not self.__is_container_for_connection(
                    metadata,
                    connection,
                )
            ):
                continue

            containers.append(
                (
                    file_path,
                    f"{metadata.layer_name} (id={metadata.resource_id})",
                )
            )

        return containers

    def purge_cache(self) -> bool:
        logger = logging.getLogger(PLUGIN_NAME)

        need_check_size = self.cache_max_size != -1
        need_check_date = self.cache_duration != -1
        if not need_check_size and not need_check_date:
            logger.debug("Cache limits is disabled")
            return True

        self.__refresh_detached_storage_index()
        report = StorageCleanupService(
            Path(self.cache_directory)
        ).clear_disposable_cache()
        logger.debug(f"Deleted {report.deleted_files} indexed cache files")

        return not report.errors

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

    def __connection_cache_paths(self, connection) -> List[Path]:
        cache_root = Path(self.cache_directory)
        connection_ids = {
            connection_id
            for connection_id in (
                connection.domain_uuid,
                connection.id,
                *connection.old_connection_ids,
            )
            if connection_id
        }
        result = {
            cache_root / connection_id for connection_id in connection_ids
        }

        for file_path in cache_root.glob("**/*.gpkg"):
            try:
                metadata = container_metadata(file_path)
            except Exception:
                continue

            if self.__is_container_for_connection(metadata, connection):
                result.add(file_path)
                result.update(file_path.parent.glob(f"{file_path.name}-*"))

        return list(result)

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

    def __is_file_used_by_project(self, file_path: Path) -> bool:
        return file_path in self.__project_container_paths()

    def __is_storage_metadata_file(self, file_path: Path) -> bool:
        file_name = file_path.name
        return (
            file_name == "storage.sqlite"
            or file_name.startswith("storage.sqlite-")
            or file_name == ".storage_migration.lock"
        )

    def __project_container_paths(self) -> List[Path]:
        if self.__project_containers is None:
            self.__project_containers = [
                container_path(layer)
                for layer in QgsProject().instance().mapLayers().values()
                if is_ngw_container(layer)
            ]

        return self.__project_containers

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

        if old_base == new_base:
            migrator = LegacyCacheMigrator(new_base, QgisProjectStorageUsage())
            try:
                report = migrator.migrate()
            except Exception:
                logging.getLogger(PLUGIN_NAME).exception(
                    "Could not migrate legacy cache"
                )
                return False
            return len(report.errors) == 0

        for directory in old_base.glob("*"):
            if not self.__is_uuid(directory.name):
                continue

            for gpkg_file in self.__legacy_container_files(directory):
                if not self.__migrate_legacy_container(
                    gpkg_file,
                    new_base,
                    directory.name,
                    gpkg_file.stem,
                ):
                    return False

            if old_base != new_base:
                self.__remove_empty_dirs(directory)

        if not any(old_base.iterdir()):
            old_base.rmdir()

        return True

    def __legacy_container_files(self, instance_directory: Path) -> List[Path]:
        return list(instance_directory.glob("*.gpkg"))

    def __migrate_legacy_container(
        self,
        container_file: Path,
        new_base: Path,
        fallback_instance_uuid: str,
        fallback_resource_id: Union[int, str],
    ) -> bool:
        fallback_resource_id_value = self.__parse_int(fallback_resource_id)
        try:
            metadata = container_metadata(container_file)
            instance_uuid = metadata.instance_id or fallback_instance_uuid
            resource_id = metadata.resource_id or fallback_resource_id_value
            connection_id = metadata.connection_id
        except Exception:
            instance_uuid = fallback_instance_uuid
            resource_id = fallback_resource_id_value
            connection_id = None
        if resource_id is None:
            logging.getLogger(PLUGIN_NAME).warning(
                "Could not determine resource id for legacy detached container: "
                f"{container_file}"
            )
            return True

        storage_service = DetachedStorageService(new_base)
        target_path = storage_service.container_path(
            instance_uuid, resource_id
        )
        if target_path.exists():
            return True

        try:
            is_registered = storage_service.register_detached_container(
                instance_uuid,
                resource_id,
                connection_id=connection_id,
                container_path=container_file,
                is_used_by_project=self.__is_file_used_by_project(
                    container_file
                ),
            )
            if not is_registered:
                return True
            self.__move_detached_container_service_files(
                container_file,
                target_path,
            )
            container_file.unlink(missing_ok=True)
        except Exception:
            logging.getLogger(PLUGIN_NAME).exception(
                "Could not migrate legacy detached container"
            )
            return False

        return True

    def __refresh_detached_storage_index(self) -> None:
        for file_path in Path(self.cache_directory).glob("**/*.gpkg"):
            try:
                metadata = container_metadata(file_path)
            except Exception:
                continue

            canonical_path = self.__storage_service.container_path(
                metadata.instance_id,
                metadata.resource_id,
            )
            if file_path != canonical_path:
                continue

            self.__storage_service.register_detached_container(
                metadata.instance_id,
                metadata.resource_id,
                connection_id=metadata.connection_id,
                container_path=file_path,
                is_used_by_project=self.__is_file_used_by_project(file_path),
            )

    def __parse_int(self, value: object) -> Optional[int]:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def __is_uuid(self, name: str) -> bool:
        return bool(self.__uuid_pattern.match(name))
