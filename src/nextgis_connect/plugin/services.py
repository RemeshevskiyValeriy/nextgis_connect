from qgis.core import QgsApplication

from nextgis_connect.features.synchronization.infrastructure.storage.cache_maintenance_service import (
    CacheMaintenanceService,
)
from nextgis_connect.legacy.detached_editing.detached_editing import (
    DetachedEditing,
)
from nextgis_connect.legacy.ngw_connection.application.connections_manager import (
    NgwConnectionsManager,
)
from nextgis_connect.legacy.settings.tasks.purge_ng_connect_cache_task import (
    PurgeNgConnectCacheTask,
)
from nextgis_connect.platform.tasks import (
    NgConnectTaskManager,
)
from nextgis_connect.plugin.service_container import ServiceContainer


def initialize_connections() -> None:
    """Initialize connection settings and migrations."""
    connections_manager = NgwConnectionsManager()
    if connections_manager.is_migrated:
        CacheMaintenanceService().reassign_container_connection_ids(
            connections_manager.connections
        )
    connections_manager.clear_old_connections_if_converted()


def create_service_container() -> ServiceContainer:
    """Create the plugin service container.

    :return: Service container with core runtime services.
    """
    return ServiceContainer(task_manager=NgConnectTaskManager())


def create_detached_editing() -> DetachedEditing:
    """Create the detached editing service.

    :return: Detached editing service.
    """
    return DetachedEditing()


def schedule_cache_purging() -> PurgeNgConnectCacheTask:
    """Schedule cache purging in the QGIS task manager.

    :return: Scheduled cache purging task.
    """
    purge_cache_task = PurgeNgConnectCacheTask()
    task_manager = QgsApplication.taskManager()
    assert task_manager is not None
    task_manager.addTask(purge_cache_task)
    return purge_cache_task
