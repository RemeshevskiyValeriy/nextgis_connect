# NextGIS Connect
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

from contextlib import ExitStack, contextmanager
from typing import Iterator, Tuple
from unittest import mock

import pytest

from nextgis_connect.legacy.ngw.core.ngw_vector_layer import NGWVectorLayer
from nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis import (
    NGWUpdateVectorLayer,
)
from nextgis_connect.legacy.ngw.qgis.qgis_ngw_connection import (
    NgwServerFeature,
)
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job_error import (
    JobError,
)
from nextgis_connect.platform.qgis.compat import GeometryType


def test_set_versioning_enabled_puts_minimal_payload(qgis_app) -> None:
    del qgis_app

    ngw_layer, connection = _vector_layer(is_versioning_enabled=True)

    ngw_layer.set_versioning_enabled(False)

    connection.put.assert_called_once_with(
        "/api/resource/7",
        params={
            "feature_layer": {
                "versioning": {
                    "enabled": False,
                },
            },
        },
    )
    assert not ngw_layer.is_versioning_enabled


def test_update_vector_layer_restores_versioning_around_replace(
    qgis_app,
) -> None:
    del qgis_app

    ngw_layer, connection = _vector_layer(is_versioning_enabled=True)
    job = NGWUpdateVectorLayer(ngw_layer, _qgis_layer())

    with _prepared_update_job(job):
        job._do()

    put_calls = connection.put.call_args_list
    assert len(put_calls) == 3
    assert put_calls[0] == _versioning_put_call(False)
    assert put_calls[1].args[0] == "https://example.test/api/resource/7"
    assert put_calls[1].kwargs["is_lunkwill"] is True
    assert put_calls[2] == _versioning_put_call(True)
    assert ngw_layer.is_versioning_enabled


def test_update_vector_layer_restores_versioning_after_replace_error(
    qgis_app,
) -> None:
    del qgis_app

    ngw_layer, connection = _vector_layer(is_versioning_enabled=True)
    connection.put.side_effect = [None, RuntimeError("replace failed"), None]
    job = NGWUpdateVectorLayer(ngw_layer, _qgis_layer())

    with pytest.raises(RuntimeError, match="replace failed"):
        with _prepared_update_job(job):
            job._do()

    put_calls = connection.put.call_args_list
    assert len(put_calls) == 3
    assert put_calls[0] == _versioning_put_call(False)
    assert put_calls[2] == _versioning_put_call(True)
    assert ngw_layer.is_versioning_enabled


def test_update_vector_layer_keeps_replace_error_when_restore_fails(
    qgis_app,
) -> None:
    del qgis_app

    ngw_layer, connection = _vector_layer(is_versioning_enabled=True)
    restore_error = RuntimeError("restore failed")
    connection.put.side_effect = [
        None,
        RuntimeError("replace failed"),
        restore_error,
    ]
    job = NGWUpdateVectorLayer(ngw_layer, _qgis_layer())
    warnings = []
    job.warningOccurred.connect(warnings.append)

    with pytest.raises(RuntimeError, match="replace failed"):
        with _prepared_update_job(job):
            job._do()

    assert warnings == [restore_error]


def test_update_vector_layer_does_not_toggle_disabled_versioning(
    qgis_app,
) -> None:
    del qgis_app

    ngw_layer, connection = _vector_layer(is_versioning_enabled=False)
    job = NGWUpdateVectorLayer(ngw_layer, _qgis_layer())

    with _prepared_update_job(job):
        job._do()

    put_calls = connection.put.call_args_list
    assert len(put_calls) == 1
    assert put_calls[0].args[0] == "https://example.test/api/resource/7"
    assert put_calls[0].kwargs["is_lunkwill"] is True


def test_update_no_geometry_versioned_layer_requires_dev8(qgis_app) -> None:
    del qgis_app

    ngw_layer, connection = _vector_layer(
        is_versioning_enabled=True,
        geometry_type="NONE",
    )
    connection.has_support_for_feature.return_value = False
    qgis_layer = _qgis_layer()
    qgis_layer.geometryType.return_value = GeometryType.Null
    job = NGWUpdateVectorLayer(ngw_layer, qgis_layer)

    with pytest.raises(JobError, match=r"5\.5\.0\.dev8"):
        job._do()

    connection.has_support_for_feature.assert_called_once_with(
        NgwServerFeature.NO_GEOMETRY_LAYER_VERSIONING
    )
    connection.tus_upload_file.assert_not_called()


def _vector_layer(
    is_versioning_enabled: bool,
    geometry_type: str = "POINT",
) -> Tuple[NGWVectorLayer, mock.Mock]:
    connection = mock.Mock()
    connection.connection_id = "test-connection"
    connection.server_url = "https://example.test/"
    connection.tus_upload_file.return_value = {"id": "upload"}

    factory = mock.Mock()
    factory.connection = connection

    ngw_layer = NGWVectorLayer(
        factory,
        {
            "resource": {
                "id": 7,
                "cls": "vector_layer",
                "parent": None,
                "owner_user": None,
                "display_name": "Remote layer",
                "description": "",
                "children": False,
                "interfaces": [],
            },
            "feature_layer": {
                "fields": [],
                "versioning": {
                    "enabled": is_versioning_enabled,
                },
            },
            "vector_layer": {
                "srs": {
                    "id": 3857,
                },
                "geometry_type": geometry_type,
            },
        },
    )
    factory.get_resource.return_value = ngw_layer

    return ngw_layer, connection


def _qgis_layer() -> mock.Mock:
    qgis_layer = mock.Mock()
    qgis_layer.name.return_value = "Local layer"
    qgis_layer.fields.return_value = []
    return qgis_layer


@contextmanager
def _prepared_update_job(job: NGWUpdateVectorLayer) -> Iterator[None]:
    with ExitStack() as stack:
        stack.enter_context(
            mock.patch.object(job, "_ensure_no_geometry_supported")
        )
        stack.enter_context(
            mock.patch.object(
                job,
                "isSuitableLayer",
                return_value=job.SUITABLE_LAYER,
            )
        )
        stack.enter_context(
            mock.patch.object(
                job,
                "prepareImportVectorFile",
                return_value=("/tmp/fake.gpkg", None, None),
            )
        )
        stack.enter_context(
            mock.patch(
                "nextgis_connect.legacy.ngw.qgis.ngw_resource_model_4qgis.os.remove"
            )
        )
        yield


def _versioning_put_call(enabled: bool) -> object:
    return mock.call(
        "/api/resource/7",
        params={
            "feature_layer": {
                "versioning": {
                    "enabled": enabled,
                },
            },
        },
    )
