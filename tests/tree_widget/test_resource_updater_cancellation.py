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

from types import SimpleNamespace
from typing import List, Optional

import pytest

from nextgis_connect.legacy.ngw.qt import qt_ngw_resource_model_job
from nextgis_connect.legacy.ngw.qt.qt_ngw_resource_model_job import (
    NGWResourceModelJobResult,
    NGWResourceUpdater,
)
from nextgis_connect.legacy.tree_widget.model import QNGWResourceTreeModelBase
from nextgis_connect.platform.qgis.errors import NgConnectError


class _Resource:
    def __init__(
        self,
        resource_id: int,
        parent_id: int,
        children: Optional[List["_Resource"]] = None,
    ) -> None:
        if children is None:
            children = []

        self.resource_id = resource_id
        self.parent_id = parent_id
        self.children = children
        self.common = SimpleNamespace(parent=parent_id)

    def get_children(self, feedback):
        del feedback
        return self.children


class _CancelingResource(_Resource):
    def get_children(self, feedback):
        feedback.cancel()
        raise NgConnectError("Request was canceled")


class _ErroredJob:
    def __init__(self, result: NGWResourceModelJobResult) -> None:
        self.model_response = None
        self._result = result

    def error(self) -> NgConnectError:
        return NgConnectError("Request was canceled")

    def getJobId(self) -> str:
        return NGWResourceUpdater.__name__

    def getResult(self) -> NGWResourceModelJobResult:
        return self._result


def test_canceled_recursive_fetch_drops_partial_resources(
    monkeypatch,
) -> None:
    group_resource = _CancelingResource(2, 1)
    root_resource = _Resource(1, 0, [group_resource])
    updater = NGWResourceUpdater(root_resource, [], recursive=True)

    monkeypatch.setattr(
        qt_ngw_resource_model_job,
        "NGWGroupResource",
        _CancelingResource,
    )

    with pytest.raises(NgConnectError, match="Request was canceled"):
        updater._do()

    assert updater.result.added_resources == []
    assert updater.result.dangling_resources == []
    assert updater.result.main_resource_id == -1


def test_errored_job_result_is_not_applied_to_tree(qgis_app) -> None:
    del qgis_app

    model = QNGWResourceTreeModelBase()
    result = NGWResourceModelJobResult()
    result.putAddedResource(_Resource(1, 0), is_main=True)
    job = _ErroredJob(result)

    model.processJobResult(job)

    assert model.rowCount() == 0
