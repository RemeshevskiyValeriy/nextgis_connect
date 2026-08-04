from qgis.PyQt.QtWidgets import QMenu, QToolButton

from nextgis_connect.legacy.shell.presentation.dock.ng_connect_dock import (
    NGWPanelToolBar,
)


class TestResourceToolbar:
    def test_configured_menu_width_does_not_depend_on_menu_presence(
        self,
        qgis_app,
    ) -> None:
        del qgis_app
        toolbar = NGWPanelToolBar()
        button = QToolButton(toolbar)
        button.setProperty("NgConnectPanelUseMenuButtonWidth", True)
        toolbar.addWidget(button)

        toolbar.fix_icons_size()

        width_without_menu = button.width()

        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        button.setMenu(QMenu(toolbar))
        toolbar.fix_icons_size()

        assert width_without_menu == NGWPanelToolBar.MENU_BUTTON_WIDTH
        assert button.width() == width_without_menu

        toolbar.deleteLater()
