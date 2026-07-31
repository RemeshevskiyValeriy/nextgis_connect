from nextgis_connect.features.synchronization.infrastructure.storage.cache_maintenance_service import (
    CacheMaintenanceService,
)
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.tasks import NgConnectTask


class PurgeNgConnectCacheTask(NgConnectTask):
    def __init__(self):
        super().__init__(flags=NgConnectTask.Flags())
        self.setDescription(self.tr("Clearing NextGIS Connect cache"))

    def run(self) -> bool:
        if not super().run():
            return False

        logger.debug("<b>Purging cache</b>")

        try:
            cache_service = CacheMaintenanceService()
            cache_service.purge_cache()
        except Exception:
            logger.exception("An error occurred while cache purging")
            return False

        return True
