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

import xml.etree.ElementTree as ElementTree  # nosec B405
from pathlib import Path
from typing import Union

XmlParseError = ElementTree.ParseError
XmlElement = ElementTree.Element


def parse_xml_bytes(payload: bytes) -> ElementTree.Element:
    """Parse trusted plugin XML payload bytes."""
    return ElementTree.fromstring(payload)  # nosec B314


def parse_xml_file(path: Union[Path, str]) -> ElementTree.Element:
    """Parse a local XML sidecar file."""
    return ElementTree.parse(str(path)).getroot()  # nosec B314


def create_xml_element(tag: str) -> XmlElement:
    """Create an XML element."""
    return ElementTree.Element(tag)


def create_xml_subelement(root: XmlElement, tag: str) -> XmlElement:
    """Create an XML subelement."""
    return ElementTree.SubElement(root, tag)


def write_xml_tree(
    root: XmlElement,
    output_path: Path,
    *,
    xml_declaration: bool,
) -> None:
    """Write an XML document to disk."""
    xml_tree = ElementTree.ElementTree(root)
    ElementTree.indent(xml_tree, space="  ")
    xml_tree.write(
        str(output_path),
        encoding="utf-8",
        xml_declaration=xml_declaration,
    )
