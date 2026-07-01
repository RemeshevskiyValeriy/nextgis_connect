import configparser
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional

from nextgis_connect.compat import parse_version
from nextgis_connect.core.constants import PACKAGE_NAME, PLUGIN_NAME
from nextgis_connect.ng_connect_interface import NgConnectInterface


class QgisPluginRepositoryParser:
    @classmethod
    def latest_version(cls, payload: bytes) -> Optional[str]:
        xml_root = ET.fromstring(payload)

        latest_version = None
        latest_parsed_version = None
        for plugin in xml_root.findall(".//pyqgis_plugin"):
            name = plugin.attrib.get("name") or plugin.findtext("name") or ""
            file_name = (
                plugin.findtext("file_name")
                or plugin.findtext("package_name")
                or ""
            )
            if name != PLUGIN_NAME and file_name != PACKAGE_NAME:
                continue

            version_string = (
                plugin.attrib.get("version")
                or plugin.findtext("version")
                or ""
            ).strip()
            if len(version_string) == 0:
                continue

            parsed_version = parse_version(version_string)
            if (
                latest_parsed_version is None
                or parsed_version > latest_parsed_version
            ):
                latest_version = version_string
                latest_parsed_version = parsed_version

        return latest_version


class PluginVersionProvider:
    @classmethod
    def current_version(cls) -> str:
        try:
            return NgConnectInterface.instance().version
        except Exception:
            metadata_path = (
                Path(__file__).resolve().parents[3] / "metadata.txt"
            )
            metadata = configparser.ConfigParser()
            metadata.read(str(metadata_path), encoding="utf-8")
            return metadata.get("general", "version")
