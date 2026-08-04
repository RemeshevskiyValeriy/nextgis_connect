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

import pytest
from qgis.core import Qgis

from nextgis_connect.legacy.shell.presentation.dock.ng_connect_dock import (
    NgConnectDock,
)
from nextgis_connect.platform.qgis.errors import NgwError


@pytest.mark.parametrize("job_name", [None, ""])
def test_reset_model_error_stops_root_loading(job_name) -> None:
    calls = []
    error = NgwError("Connection error", is_network_problem=True)
    dock = SimpleNamespace(
        _NgConnectDock__root_children_loading_parent_id=None,
        _NgConnectDock__root_loading_cancel_requested=False,
        unblock_gui=lambda: calls.append("unblock"),
        _NgConnectDock__show_root_loading_error=lambda exception: calls.append(
            ("root_error", exception)
        ),
    )
    process_exception = NgConnectDock._NgConnectDock__model_exception_process

    process_exception(
        dock,
        job_name,
        "",
        error,
        Qgis.MessageLevel.Critical,
    )

    assert calls == ["unblock", ("root_error", error)]
