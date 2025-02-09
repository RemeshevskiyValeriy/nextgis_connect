import platform
from enum import Enum, auto
from itertools import islice
from typing import Optional, Tuple, Union, cast

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsSettings,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import QByteArray, QLocale, QMimeData, Qt, QUrl
from qgis.PyQt.QtGui import QClipboard, QDesktopServices
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
)
from qgis.utils import iface

from nextgis_connect.compat import QGIS_3_30
from nextgis_connect.settings.ng_connect_settings import NgConnectSettings

iface = cast(QgisInterface, iface)


class SupportStatus(Enum):
    OLD_NGW = auto()
    OLD_CONNECT = auto()
    SUPPORTED = auto()


class ChooserDialog(QDialog):
    def __init__(self, options):
        super().__init__()
        self.options = options

        self.setLayout(QVBoxLayout())

        self.list = QListWidget()
        self.list.setSelectionMode(QListWidget.MultiSelection)
        self.list.setSelectionBehavior(QListWidget.SelectItems)
        self.layout().addWidget(self.list)

        for option in options:
            item = QListWidgetItem(option)
            self.list.addItem(item)

        self.list.setCurrentRow(0)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.Ok, Qt.Orientation.Horizontal, self
        )
        ok_button = self.btn_box.button(QDialogButtonBox.Ok)
        assert ok_button is not None
        ok_button.clicked.connect(self.accept)
        self.layout().addWidget(self.btn_box)

        self.seleced_options = []

    def accept(self):
        self.seleced_options = [
            item.text() for item in self.list.selectedItems()
        ]
        super().accept()


def open_plugin_help():
    domain = "ru" if QgsApplication.instance().locale() == "ru" else "com"
    QDesktopServices.openUrl(
        QUrl(f"https://docs.nextgis.{domain}/docs_ngconnect/source/toc.html")
    )


def set_clipboard_data(
    mime_type: str, data: Union[QByteArray, bytes, bytearray], text: str
):
    mime_data = QMimeData()
    mime_data.setData(mime_type, data)
    if len(text) > 0:
        mime_data.setText(text)

    clipboard = QgsApplication.clipboard()
    assert clipboard is not None
    if platform.system() == "Linux":
        selection_mode = QClipboard.Mode.Selection
        clipboard.setMimeData(mime_data, selection_mode)
    clipboard.setMimeData(mime_data, QClipboard.Mode.Clipboard)


def is_version_supported(current_version_string: str) -> SupportStatus:
    def version_to_tuple(version: str) -> Tuple[int, int]:
        minor, major = islice(map(int, version.split(".")), 2)
        return minor, major

    def version_shift(version: Tuple[int, int], shift: int) -> Tuple[int, int]:
        version_number = version[0] * 10 + version[1]
        shifted_version = version_number + shift
        return shifted_version // 10, shifted_version % 10

    current_version = version_to_tuple(current_version_string)

    settings = NgConnectSettings()
    if settings.is_developer_mode:
        return SupportStatus.SUPPORTED

    supported_version_string = settings.supported_ngw_version
    supported_version = version_to_tuple(supported_version_string)

    oldest_version = version_shift(supported_version, -2)
    newest_version = version_shift(supported_version, 1)

    if current_version < oldest_version:
        return SupportStatus.OLD_NGW

    if current_version > newest_version:
        return SupportStatus.OLD_CONNECT

    return SupportStatus.SUPPORTED


def get_project_import_export_menu() -> Optional[QMenu]:
    """
    Returns the application Project - Import/Export sub menu
    """
    if Qgis.versionInt() >= QGIS_3_30:
        return iface.projectImportExportMenu()

    project_menu = iface.projectMenu()
    matches = [
        m
        for m in project_menu.children()
        if m.objectName() == "menuImport_Export"
    ]
    if matches:
        return matches[0]

    return None


def add_project_export_action(project_export_action: QAction) -> None:
    """
    Decides how to add action of project export to the Project - Import/Export sub menu
    """
    if Qgis.versionInt() >= QGIS_3_30:
        iface.addProjectExportAction(project_export_action)
    else:
        import_export_menu = get_project_import_export_menu()
        if import_export_menu:
            export_separators = [
                action
                for action in import_export_menu.actions()
                if action.isSeparator()
            ]
            if export_separators:
                import_export_menu.insertAction(
                    export_separators[0],
                    project_export_action,
                )
            else:
                import_export_menu.addAction(project_export_action)


def locale() -> str:
    override_locale = QgsSettings().value(
        "locale/overrideFlag", defaultValue=False, type=bool
    )
    if not override_locale:
        locale_full_name = QLocale.system().name()
    else:
        locale_full_name = QgsSettings().value("locale/userLocale", "")
    locale = locale_full_name[0:2].lower()
    return locale


def nextgis_domain(subdomain: Optional[str] = None) -> str:
    speaks_russian = locale() in ["be", "kk", "ky", "ru", "uk"]
    if subdomain is None:
        subdomain = ""
    elif not subdomain.endswith("."):
        subdomain += "."
    return f"https://{subdomain}nextgis.{'ru' if speaks_russian else 'com'}"


def utm_tags(utm_medium: str, *, utm_campaign: str = "constant") -> str:
    utm = (
        f"utm_source=qgis_plugin&utm_medium={utm_medium}"
        f"&utm_campaign={utm_campaign}&utm_term=nextgis_connect"
        f"&utm_content={locale()}"
    )
    return utm
