from pathlib import Path
from typing import Callable, cast
from unittest.mock import Mock

import qgis.utils
from qgis.core import QgsApplication
from qgis.gui import QgisInterface
from qgis.PyQt.QtWidgets import QScrollArea, QTabWidget, QWidget

from nextgis_connect.legacy.detached_editing.identification.settings import (
    IdentificationSettings,
)
from nextgis_connect.legacy.detached_editing.identification.types import (
    IdentificationTab,
)
from nextgis_connect.legacy.detached_editing.identification.ui.identification_results_widget import (
    IdentificationResultsWidget,
)
from nextgis_connect.shared.constants import PACKAGE_NAME


class _IdentificationWidgetHarness:
    def __init__(self, current_tab: IdentificationTab) -> None:
        self.tab_widget = QTabWidget()
        self._is_changing_tab_availability = False
        self.overlay_update_count = 0

        self.tab_widget.addTab(QWidget(self.tab_widget), "Attributes")
        self.tab_widget.addTab(QWidget(self.tab_widget), "Attachments")
        self.tab_widget.addTab(QWidget(self.tab_widget), "Description")
        self.tab_widget.setCurrentIndex(current_tab)
        self.tab_widget.currentChanged.connect(self._on_tab_changed)

    def set_feature_data_tabs_enabled(self, enabled: bool) -> None:
        method_name = (
            "_IdentificationResultsWidget__set_feature_data_tabs_enabled"
        )
        method = cast(
            Callable[["_IdentificationWidgetHarness", bool], None],
            getattr(IdentificationResultsWidget, method_name),
        )
        method(self, enabled)

    def close(self) -> None:
        self.tab_widget.close()
        self.tab_widget.deleteLater()

    def _update_overlay_geometry(self) -> None:
        self.overlay_update_count += 1

    def _on_tab_changed(self, selected_tab: int) -> None:
        method_name = "_IdentificationResultsWidget__on_tab_changed"
        method = cast(
            Callable[["_IdentificationWidgetHarness", int], None],
            getattr(IdentificationResultsWidget, method_name),
        )
        method(self, selected_tab)


class TestIdentificationResultsWidget:
    def test_unload_is_idempotent_for_open_dock(
        self, qgis_iface: QgisInterface
    ) -> None:
        plugin = Mock()
        plugin.path = Path(__file__).resolve().parents[2] / (
            "src/nextgis_connect"
        )
        previous_plugin = qgis.utils.plugins.get(PACKAGE_NAME)
        qgis.utils.plugins[PACKAGE_NAME] = plugin

        widget = IdentificationResultsWidget(qgis_iface.mapCanvas())
        try:
            assert isinstance(widget.attributes_scroll_area, QScrollArea)
            assert widget.attributes_scroll_area.widgetResizable()
            assert (
                widget.attributes_tab.layout().indexOf(
                    widget.attributes_scroll_area
                )
                >= 0
            )

            widget.unload()
            widget.unload()
        finally:
            widget.close()
            widget.deleteLater()
            if previous_plugin is None:
                qgis.utils.plugins.pop(PACKAGE_NAME, None)
            else:
                qgis.utils.plugins[PACKAGE_NAME] = previous_plugin

    def test_feature_data_tabs_can_be_disabled_temporarily(
        self, qgis_app: QgsApplication
    ) -> None:
        del qgis_app

        settings = IdentificationSettings()
        settings.last_used_tab = IdentificationTab.ATTACHMENTS

        widget = _IdentificationWidgetHarness(settings.last_used_tab)
        try:
            widget.set_feature_data_tabs_enabled(False)

            assert widget.tab_widget.currentIndex() == (
                IdentificationTab.ATTRIBUTES
            )
            assert not widget.tab_widget.isTabEnabled(
                IdentificationTab.ATTACHMENTS
            )
            assert not widget.tab_widget.isTabEnabled(
                IdentificationTab.DESCRIPTION
            )
            assert settings.last_used_tab == IdentificationTab.ATTACHMENTS
            assert widget.overlay_update_count == 1

            widget.set_feature_data_tabs_enabled(True)

            assert widget.tab_widget.currentIndex() == (
                IdentificationTab.ATTACHMENTS
            )
            assert widget.tab_widget.isTabEnabled(
                IdentificationTab.ATTACHMENTS
            )
            assert widget.tab_widget.isTabEnabled(
                IdentificationTab.DESCRIPTION
            )
        finally:
            widget.close()
