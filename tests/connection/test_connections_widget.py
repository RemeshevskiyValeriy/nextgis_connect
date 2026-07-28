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
