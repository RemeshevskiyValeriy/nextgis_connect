from pathlib import Path
from unittest.mock import Mock

import pytest
from qgis.core import QgsApplication, QgsRasterBlockFeedback

from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    NGWUpdateRasterLayer,
    NGWUpdateVectorLayer,
    QGISProjectUploader,
    QGISResourcesUploader,
)
from nextgis_connect.legacy.ngw.qgis.raster_upload_preparer import (
    PreparedRasterFile,
)
from nextgis_connect.platform.qgis.errors import NgConnectError


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
        assert isinstance(job._feedback, QgsRasterBlockFeedback)


def test_project_upload_skips_webmap_after_cancellation(
    monkeypatch: pytest.MonkeyPatch,
    qgis_app: QgsApplication,
) -> None:
    del qgis_app

    parent_group = Mock()
    parent_group.get_children.return_value = []
    created_group = Mock()

    create_group = Mock(return_value=created_group)
    monkeypatch.setattr(
        "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis."
        "ResourceCreator.create_group",
        create_group,
    )

    job = QGISProjectUploader("Project", parent_group, Mock(), None)
    job._find_lookup_tables = Mock()
    job._check_quote = Mock()
    job._add_group_tree = Mock()
    job._add_lookup_tables = Mock()
    job.process_one_level_of_layers_tree = Mock(
        side_effect=lambda *_: job.cancel()
    )
    job.create_webmap = Mock()

    with pytest.raises(NgConnectError, match="Request was canceled"):
        job._do()

    job.create_webmap.assert_not_called()


def test_raster_preparer_receives_upload_job_feedback(
    monkeypatch: pytest.MonkeyPatch,
    qgis_app: QgsApplication,
) -> None:
    del qgis_app

    captured_feedback = []

    class DummyRasterUploadPreparer:
        def __init__(self, *, feedback=None) -> None:
            captured_feedback.append(feedback)

        def prepare(self, _layer) -> PreparedRasterFile:
            return PreparedRasterFile(
                upload_path=Path("/tmp/raster.tif"),
                is_temporary=False,
                is_archive=False,
            )

    monkeypatch.setattr(
        "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis."
        "RasterUploadPreparer",
        DummyRasterUploadPreparer,
    )

    job = QGISResourcesUploader([], Mock(), Mock())
    layer = Mock()
    layer.name.return_value = "Raster"

    job.prepareImportRasterFile(layer)

    assert captured_feedback == [job._feedback]
