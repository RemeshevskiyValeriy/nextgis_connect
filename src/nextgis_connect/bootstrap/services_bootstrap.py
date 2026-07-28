from qgis.core import QgsApplication

from nextgis_connect.bootstrap.service_container import ServiceContainer
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


def initialize_connections() -> None:
    connections_manager = NgwConnectionsManager()
    connections_manager.clear_old_connections_if_converted()


def create_service_container() -> ServiceContainer:
    return ServiceContainer(task_manager=NgConnectTaskManager())


def create_detached_editing() -> DetachedEditing:
    return DetachedEditing()


def schedule_cache_purging() -> PurgeNgConnectCacheTask:
    purge_cache_task = PurgeNgConnectCacheTask()
    task_manager = QgsApplication.taskManager()
    assert task_manager is not None
    task_manager.addTask(purge_cache_task)
    return purge_cache_task
