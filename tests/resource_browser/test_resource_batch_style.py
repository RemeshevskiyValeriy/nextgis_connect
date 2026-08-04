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

from unittest import mock

import pytest

from nextgis_connect.features.resource_browser.domain import (
    ResourceImportStyle,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_batch_style import (
    QgisResourceBatchStyleApplicator,
)
from nextgis_connect.features.resource_browser.infrastructure.qgis_resource_style import (
    QgisResourceLayerStyleApplicator,
)
from nextgis_connect.legacy.ngw.core import NGWQGISStyle, NGWResource
from nextgis_connect.platform.qgis.errors import NgConnectError


def _style(
    resource_id: int,
    name: str,
    qml: str = "<qgis/>",
    is_populated: bool = True,
) -> NGWQGISStyle:
    style = mock.Mock(spec=NGWQGISStyle)
    style.resource_id = resource_id
    style.display_name = name
    style.qml = qml
    style.is_qml_populated = is_populated
    return style


def test_batch_style_adapter_uses_shared_qgis_applicator() -> None:
    first_style = _style(1, "Zulu")
    default_style = _style(2, "Alpha")
    resource = mock.Mock(spec=NGWResource)
    resource.resource_id = 10
    model = mock.Mock()
    model.children_resources.return_value = [first_style, default_style]
    shared_applicator = mock.Mock(spec=QgisResourceLayerStyleApplicator)
    layer = mock.Mock()
    applicator = QgisResourceBatchStyleApplicator(
        model,
        shared_applicator,
    )

    applicator.apply_all(resource, layer, default_style.resource_id)

    shared_applicator.apply.assert_called_once_with(
        (
            ResourceImportStyle("Alpha", "<qgis/>"),
            ResourceImportStyle("Zulu", "<qgis/>"),
        ),
        layer,
        "Alpha",
    )


def test_batch_style_adapter_rejects_missing_qml() -> None:
    style = _style(1, "Missing", is_populated=False)
    resource = mock.Mock(spec=NGWResource)
    resource.resource_id = 10
    model = mock.Mock()
    model.children_resources.return_value = [style]
    shared_applicator = mock.Mock(spec=QgisResourceLayerStyleApplicator)
    applicator = QgisResourceBatchStyleApplicator(
        model,
        shared_applicator,
    )

    with pytest.raises(NgConnectError, match="is not downloaded"):
        applicator.apply_all(resource, mock.Mock())

    shared_applicator.apply.assert_not_called()
