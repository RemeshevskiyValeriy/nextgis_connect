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

import importlib

import qgis.utils
from qgis.PyQt.QtWidgets import QToolBar

import nextgis_connect
from nextgis_connect.shared.constants import PACKAGE_NAME


def test_plugin_package_imports(qgis_iface) -> None:
    del qgis_iface

    plugin_module = importlib.import_module("nextgis_connect.plugin.plugin")

    assert callable(nextgis_connect.classFactory)
    assert plugin_module.NgConnectPlugin is not None


def test_plugin_loads(qgis_iface) -> None:
    plugin = nextgis_connect.classFactory(qgis_iface)
    qgis.utils.plugins[PACKAGE_NAME] = plugin

    plugin._load()

    try:
        assert plugin.container is not None
    finally:
        plugin._unload()
        qgis.utils.plugins.pop(PACKAGE_NAME, None)


def test_plugin_reload_cleans_ui_resources(qgis_iface) -> None:
    from nextgis_connect.legacy.shell.presentation.dock.ng_connect_dock import (
        NgConnectDock,
    )
    from nextgis_connect.platform.qgis import utils as qgis_platform_utils

    qgis_platform_utils.iface = qgis_iface
    main_window = qgis_iface.mainWindow()
    qgis_iface.addDockWidget.side_effect = main_window.addDockWidget
    qgis_iface.removeDockWidget.side_effect = main_window.removeDockWidget
    initial_layer_action_additions = (
        qgis_iface.addCustomActionForLayerType.call_count
    )
    initial_layer_action_removals = (
        qgis_iface.removeCustomActionForLayerType.call_count
    )
    initial_project_export_additions = (
        qgis_iface.addProjectExportAction.call_count
    )
    initial_project_export_removals = (
        qgis_iface.removeProjectExportAction.call_count
    )

    for _ in range(2):
        plugin = nextgis_connect.classFactory(qgis_iface)
        qgis.utils.plugins[PACKAGE_NAME] = plugin
        plugin._load()

        try:
            assert main_window.findChildren(QToolBar, "NgConnectToolBar")
            assert main_window.findChildren(NgConnectDock, "NGConnectDock")
        finally:
            plugin._unload()
            qgis.utils.plugins.pop(PACKAGE_NAME, None)

        assert main_window.findChildren(QToolBar, "NgConnectToolBar") == []
        assert main_window.findChildren(NgConnectDock, "NGConnectDock") == []

    layer_action_additions = (
        qgis_iface.addCustomActionForLayerType.call_count
        - initial_layer_action_additions
    )
    layer_action_removals = (
        qgis_iface.removeCustomActionForLayerType.call_count
        - initial_layer_action_removals
    )
    assert layer_action_removals == layer_action_additions
    assert (
        qgis_iface.addProjectExportAction.call_count
        - initial_project_export_additions
    ) == 2
    assert (
        qgis_iface.removeProjectExportAction.call_count
        - initial_project_export_removals
    ) == 2
