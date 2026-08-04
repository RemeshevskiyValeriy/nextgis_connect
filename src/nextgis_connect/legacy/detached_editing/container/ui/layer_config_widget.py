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

from contextlib import closing
from pathlib import Path
from typing import Optional

from qgis.core import QgsMapLayer, QgsVectorLayer
from qgis.gui import (
    QgsMapCanvas,
    QgsMapLayerConfigWidget,
    QgsMapLayerConfigWidgetFactory,
)
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from nextgis_connect.legacy.detached_editing import utils
from nextgis_connect.platform.logging import logger
from nextgis_connect.platform.qgis.errors import NgConnectError
from nextgis_connect.platform.qgis.utils import wrap_sql_value
from nextgis_connect.ui_kit.icons import plugin_icon


class DetachedLayerConfigPage(QgsMapLayerConfigWidget):
    __path: Path
    __metadata: utils.DetachedContainerMetaData
    __layer: QgsVectorLayer

    def __init__(
        self,
        layer: Optional[QgsMapLayer],
        canvas: Optional[QgsMapCanvas],
        parent: Optional[QWidget],
    ) -> None:
        super().__init__(layer, canvas, parent)
        self.setPanelTitle(self.tr("NextGIS"))

        directory = Path(__file__).parent
        widget: Optional[QWidget] = None
        try:
            widget = uic.loadUi(str(directory / "layer_config_widget_base.ui"))  # type: ignore
        except FileNotFoundError as error:
            message = self.tr("An error occurred while settings UI loading")
            logger.exception(message)
            raise RuntimeError(message) from error
        if widget is None:
            message = self.tr("An error occurred in settings UI")
            logger.error(message)
            raise RuntimeError(message)

        self.__widget = widget
        self.__widget.setParent(self)

        assert isinstance(layer, QgsVectorLayer)
        self.__path = utils.container_path(layer)
        try:
            self.__metadata = utils.container_metadata(self.__path)
        except Exception:
            logger.exception(
                "An error occurred during layer metadata extracting"
            )
            raise

        self.__layer = layer

        self.__widget.autosync_checkbox.setChecked(
            self.__metadata.is_auto_sync_enabled
        )

        layout = QHBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setMargin(0)  # type: ignore
        self.setLayout(layout)
        layout.addWidget(self.__widget)

    def apply(self) -> None:
        """Called when changes to the layer need to be made"""
        new_autosync_state = self.__widget.autosync_checkbox.isChecked()
        if new_autosync_state == self.__metadata.is_auto_sync_enabled:
            return

        with closing(
            utils.make_connection(self.__path)
        ) as connection, closing(connection.cursor()) as cursor:
            cursor.execute(
                f"""
                UPDATE ngw_metadata
                SET
                    is_auto_sync_enabled={wrap_sql_value(new_autosync_state)}
                """  # nosec B608
            )

            connection.commit()

        self.__metadata = utils.container_metadata(self.__path)

        self.__layer.setCustomProperty("ngw_need_update_state", True)

    def shouldTriggerLayerRepaint(self) -> bool:
        return super().shouldTriggerLayerRepaint()

    def syncToLayer(self, layer: Optional[QgsMapLayer]) -> None:
        super().syncToLayer(layer)
        self.__metadata = utils.container_metadata(self.__path)
        self.__widget.autosync_checkbox.setChecked(
            self.__metadata.is_auto_sync_enabled
        )


class DetachedLayerConfigErrorPage(QgsMapLayerConfigWidget):
    widget: QWidget

    def __init__(
        self,
        layer: Optional[QgsMapLayer],
        canvas: Optional[QgsMapCanvas],
        parent: Optional[QWidget],
        message: Optional[str] = None,
    ) -> None:
        super().__init__(layer, canvas, parent)
        self.setPanelTitle(self.tr("NextGIS"))

        self.widget = QLabel(
            self.tr("Layer options widget was crashed")
            if message is None
            else message,
            self,
        )
        self.widget.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout()
        self.setLayout(layout)
        layout.addWidget(self.widget)

    def apply(self) -> None:
        pass


class DetachedLayerConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):
    def __init__(self):
        super().__init__("NextGIS", plugin_icon("branding/connect_logo.svg"))
        self.setSupportLayerPropertiesDialog(True)

    def __del__(self) -> None:
        logger.debug("Delete detached layer config factory")

    def supportsLayer(self, layer: Optional[QgsMapLayer]) -> bool:
        if layer is None:
            return False
        return utils.is_ngw_container(layer)

    def supportLayerPropertiesDialog(self) -> bool:
        return True

    def createWidget(
        self,
        layer: Optional[QgsMapLayer],
        canvas: Optional[QgsMapCanvas],
        dockWidget: bool = True,
        parent: Optional[QWidget] = None,
    ) -> QgsMapLayerConfigWidget:
        try:
            return DetachedLayerConfigPage(layer, canvas, parent)

        except NgConnectError as error:
            return DetachedLayerConfigErrorPage(
                layer, canvas, parent, error.user_message
            )

        except Exception:
            logger.exception("Layer settings dialog was crashed")
            return DetachedLayerConfigErrorPage(layer, canvas, parent)
