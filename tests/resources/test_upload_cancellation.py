from unittest.mock import Mock

from qgis.core import QgsApplication

from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    NGWUpdateRasterLayer,
    NGWUpdateVectorLayer,
    QGISProjectUploader,
    QGISResourcesUploader,
)


def test_upload_jobs_are_cancelable(qgis_app: QgsApplication) -> None:
    del qgis_app

    jobs = [
        QGISResourcesUploader([], Mock(), Mock()),
        QGISProjectUploader("Project", Mock(), Mock(), None),
        NGWUpdateVectorLayer(Mock(), Mock()),
        NGWUpdateRasterLayer(Mock(), Mock()),
    ]

    for job in jobs:
        job.cancel()

        assert job._feedback is not None
        assert job._feedback.isCanceled()
