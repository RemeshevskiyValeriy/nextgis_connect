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

from pathlib import Path

from nextgis_connect.legacy.ngw_connection.presentation.connections_widget import (
    NgwConnectionsWidget,
)


def test_project_containers_html_uses_labels_only() -> None:
    html = NgwConnectionsWidget._NgwConnectionsWidget__project_containers_html(
        [
            (
                Path("/tmp/cache/42.gpkg"),
                "Roads <main> (id=42)",
            )
        ]
    )

    assert html == "<ul><li>Roads &lt;main&gt; (id=42)</li></ul>"
    assert "/tmp/cache/42.gpkg" not in html
