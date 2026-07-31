from pathlib import Path
from typing import Dict, Optional

from qgis.PyQt.QtGui import QIcon

from nextgis_connect.ui_kit.icons import plugin_icon, plugin_icon_file_path


class AttachmentIconProvider:
    """Resolve and cache attachment file-type icons."""

    UNKNOWN_ICON_PATH = "attachments/unknown.svg"

    def __init__(self) -> None:
        self._icon_by_path: Dict[str, QIcon] = {}

    def icon_for_file_name(self, file_name: Optional[str]) -> QIcon:
        """Return an icon for a file name extension."""
        icon_path = self.icon_path_for_file_name(file_name)
        if icon_path not in self._icon_by_path:
            self._icon_by_path[icon_path] = plugin_icon(icon_path)
        return self._icon_by_path[icon_path]

    def icon_path_for_file_name(self, file_name: Optional[str]) -> str:
        """Return plugin icon path for a file name extension."""
        extension = self._extension(file_name)
        if extension is None:
            return self.UNKNOWN_ICON_PATH

        icon_path = f"attachments/{extension}.svg"
        if plugin_icon_file_path(icon_path).exists():
            return icon_path

        return self.UNKNOWN_ICON_PATH

    def _extension(self, file_name: Optional[str]) -> Optional[str]:
        if not file_name:
            return None

        extension = Path(file_name).suffix.lower().lstrip(".")
        if not extension:
            return None

        return extension
