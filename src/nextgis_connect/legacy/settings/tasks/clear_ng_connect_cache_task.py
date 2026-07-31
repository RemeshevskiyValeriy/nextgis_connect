from nextgis_connect.features.synchronization.infrastructure.storage.cache_maintenance_service import (
    CacheMaintenanceService,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.tasks import NgConnectTask


class ClearNgConnectCacheTask(NgConnectTask):
    def __init__(self):
        super().__init__(flags=NgConnectTask.Flags())
        self.setDescription(self.tr("Clearing NextGIS Connect cache"))

    def run(self) -> bool:
        if not super().run():
            return False

        logger.debug("<b>Clearing cache</b>")

        try:
            cache_service = CacheMaintenanceService()
            return cache_service.clear_cache()
        except Exception as error:
            logger.exception("An error occurred while cache clearing")
            self._error = error
            return False
