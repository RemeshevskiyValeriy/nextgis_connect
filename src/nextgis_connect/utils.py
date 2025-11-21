import platform
from enum import Enum, auto
from itertools import islice
from pathlib import Path
from typing import Any, Optional, Tuple, Union, cast

from qgis.core import (
    Qgis,
    QgsApplication,
    QgsSettings,
)
from qgis.gui import QgisInterface
from qgis.PyQt.QtCore import (
    QBuffer,
    QByteArray,
    QIODevice,
    QLocale,
    QMimeData,
    QSize,
    Qt,
)
from qgis.PyQt.QtGui import QClipboard, QIcon, QPainter, QPixmap
from qgis.PyQt.QtSvg import QSvgRenderer
from qgis.PyQt.QtWidgets import (
    QAction,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
)
from qgis.utils import iface

from nextgis_connect.compat import QGIS_3_30
from nextgis_connect.core.ui.about_dialog import AboutDialog
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
        self.list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.list.setSelectionBehavior(
            QListWidget.SelectionBehavior.SelectItems
        )
        self.layout().addWidget(self.list)

        for option in options:
            item = QListWidgetItem(option)
            self.list.addItem(item)

        self.list.setCurrentRow(0)

        self.btn_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok, Qt.Orientation.Horizontal, self
        )
        ok_button = self.btn_box.button(QDialogButtonBox.StandardButton.Ok)
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
    dialog = AboutDialog(str(Path(__file__).parent.name))
    dialog.exec()


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

    return locale if locale.lower() != "c" else "en"


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


def wrap_sql_value(value: Any) -> str:
    """
    Converts a Python value to a SQL-compatible string representation.

    :param value: The value to be converted.
    :type value: Any
    :return: The SQL-compatible string representation of the value.
    :rtype: str
    """
    if isinstance(value, str):
        value = value.replace("'", r"''")
        return f"'{value}'"
    if isinstance(value, bool):
        return str(value).lower()
    if value is None:
        return "NULL"
    return str(value)


def wrap_sql_table_name(value: Any) -> str:
    """
    Wraps a given value in double quotes for use as an SQL table name,
    escaping any existing double quotes within the value.

    :param value: The value to be wrapped.
    :type value: Any
    :return: The value wrapped in double quotes.
    :rtype: str
    """
    value = value.replace('"', r'""')
    return f'"{value}"'


def draw_icon(label: QLabel, icon: QIcon, *, size: int = 24) -> None:
    pixmap = icon.pixmap(icon.actualSize(QSize(size, size)))
    label.setPixmap(pixmap)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)


def render_svg_icon(
    svg_path: Path, *, color: Optional[str] = None, size: Optional[int] = None
) -> QIcon:
    """Render an SVG file into a QIcon with optional recolor and resize.

    :param svg_path: Filesystem path to the SVG file.
    :type svg_path: Path
    :param color: Color to apply instead of white fill. If None, keep the
        original fills unchanged.
    :type color: Optional[str]
    :param size: Output icon size in pixels. If None, use SVG default size.
    :type size: Optional[int]
    :returns: Rendered QIcon.
    :rtype: QIcon
    :raises ValueError: If the SVG cannot be loaded.
    """
    svg_content = svg_path.read_text(encoding="utf-8")

    # Replace only pure white fills to preserve multi-colored icons
    if color:
        modified_svg = svg_content.replace('fill="#ffffff"', f'fill="{color}"')
        modified_svg = modified_svg.replace("fill:#ffffff", f"fill:{color}")
    else:
        modified_svg = svg_content

    byte_array = QByteArray(modified_svg.encode("utf-8"))
    renderer = QSvgRenderer()
    if not renderer.load(byte_array):
        message = f"Failed to load SVG: {svg_path}"
        raise ValueError(message)

    target_size = renderer.defaultSize() if size is None else QSize(size, size)
    pixmap = QPixmap(target_size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()

    return QIcon(pixmap)


def material_icon(
    name: str, *, color: str = "", size: Optional[int] = None
) -> QIcon:
    """Return a material icon as QIcon, optionally recolored and resized.

    :param name: Name of the material icon (without .svg extension).
    :type name: str
    :param color: Color to apply to the icon (hex string).
    :type color: str
    :param size: Size of the icon in pixels.
    :type size: Optional[int]
    :returns: QIcon instance for the material icon.
    :rtype: QIcon
    :raises FileNotFoundError: If the SVG file is not found.
    :raises ValueError: If the SVG cannot be loaded.
    """
    material_icons_path = Path(__file__).parent / "icons" / "material"

    svg_path = None
    for path in material_icons_path.glob(f"{name}*"):
        if path.is_file():
            svg_path = path
            break

    if svg_path is None:
        message = f"SVG file not found: {svg_path}"
        raise FileNotFoundError(message)

    effective_color = color or QgsApplication.palette().text().color().name()
    return render_svg_icon(svg_path, color=effective_color, size=size)


def icon_to_base64(icon: QIcon, size: Optional[int] = None) -> str:
    """Convert a QIcon to a base64-encoded string.

    :param icon: QIcon to convert.
    :type icon: QIcon
    :returns: Base64-encoded string of the icon.
    :rtype: str
    """
    icon_size = QSize(32, 32) if size is None else QSize(size, size)
    pixmap = icon.pixmap(icon_size)

    buffer = QByteArray()
    qbuffer = QBuffer(buffer)
    qbuffer.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(qbuffer, "PNG")
    qbuffer.close()

    data = buffer.toBase64().data()
    if not isinstance(data, str):
        data = data.decode("utf-8")

    return "data:image/png;base64, " + data
