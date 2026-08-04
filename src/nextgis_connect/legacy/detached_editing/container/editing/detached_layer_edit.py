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

from qgis.core import QgsVectorLayer, edit

from nextgis_connect.legacy.detached_editing.container.container import (
    DetachedContainer,
)
from nextgis_connect.legacy.detached_editing.utils import (
    container_path,
    is_ngw_container,
)


class DetachedLayerEdit(edit):
    def __init__(self, layer: QgsVectorLayer) -> None:
        super().__init__(layer)
        self.container = None
        if is_ngw_container(layer):
            path = container_path(layer)
            self.container = DetachedContainer(path)
            self.container.add_layer(layer)
            layer.setReadOnly(False)

    def __exit__(self, ex_type, ex_value, traceback) -> bool:
        result = super().__exit__(ex_type, ex_value, traceback)

        if self.container is not None:
            self.container.delete_layer(self.layer.id())
            self.container = None

        return result
