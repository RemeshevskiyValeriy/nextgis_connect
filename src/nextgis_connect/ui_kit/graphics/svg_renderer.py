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

import re
from pathlib import Path
from typing import Any, ClassVar, Dict, Mapping, Optional, Set, Union

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import (
    QByteArray,
    QFile,
    QIODevice,
    QObject,
    QRectF,
    QSize,
)
from qgis.PyQt.QtGui import QColor, QPainter
from qgis.PyQt.QtSvg import QSvgRenderer

SvgSource = Union[str, Path, QByteArray, bytes]
ColorSource = Union[QColor, str, Any]
ReplacementValue = Union[str, QColor, Any]


class CustomSvgRenderer(QObject):
    """Render SVG content with text replacements.

    Load SVG data from files or bytes, apply color and custom text
    replacements, and render through an internal ``QSvgRenderer``.
    """

    _NON_REPLACEABLE_COLORS: ClassVar[Set[str]] = {
        "",
        "none",
        "transparent",
        "inherit",
        "initial",
        "unset",
        "currentcolor",
    }

    def __init__(
        self,
        source: Optional[SvgSource] = None,
        parent: Optional[QObject] = None,
        themed: bool = False,
    ) -> None:
        """Initialize the SVG renderer.

        :param source: SVG source to load.
        :param parent: Parent object.
        :param themed: Whether to resolve colors from the active theme.
        """
        super().__init__(parent)

        self._renderer = QSvgRenderer(self)
        self._original_data: Optional[QByteArray] = None
        self._replacements: Dict[str, str] = {}

        self._fill_color: Optional[QColor] = None
        self._stroke_color: Optional[QColor] = None
        self._themed = themed
        self._is_dirty = False
        self._last_palette_key: Optional[str] = None

        if source is not None:
            self.load(source)

    def load(self, source: SvgSource) -> bool:
        """Load SVG content.

        :param source: SVG source to load.
        :return: ``True`` when the renderer accepts the SVG data.
        """
        self._original_data = self._read_source(source)
        self._is_dirty = True

        return self._reload_renderer()

    def render(self, painter: QPainter, *args: Any) -> None:
        """Render SVG content.

        :param painter: Painter used for rendering.
        :param args: Arguments passed to ``QSvgRenderer.render``.
        """
        self._ensure_renderer_updated()
        self._renderer.render(painter, *args)

    def default_size(self) -> QSize:
        """Return the default SVG document size.

        :return: Default SVG size.
        """
        self._ensure_renderer_updated()

        return self._renderer.defaultSize()

    @property
    def themed(self) -> bool:
        """Return whether themed replacements are enabled.

        :return: ``True`` when themed replacements are enabled.
        """
        return self._themed

    @themed.setter
    def themed(self, value: bool) -> None:
        """Set whether themed replacements are enabled.

        :param value: Whether themed replacements are enabled.
        """
        self.set_themed(value)

    def size_for(
        self, *, height: Optional[int] = None, width: Optional[int] = None
    ) -> QSize:
        """Return the SVG size scaled to a target dimension.

        :param height: Target height in pixels.
        :param width: Target width in pixels.
        :return: Scaled SVG size.
        """
        default_size = self.default_size()

        if height is not None and width is not None:
            return QSize(width, height)

        if height is not None:
            scale_factor = height / default_size.height()
            return QSize(
                round(default_size.width() * scale_factor),
                round(default_size.height() * scale_factor),
            )

        if width is not None:
            scale_factor = width / default_size.width()
            return QSize(
                round(default_size.width() * scale_factor),
                round(default_size.height() * scale_factor),
            )

        return default_size

    def view_box(self) -> QRectF:
        """Return the SVG view box rectangle.

        :return: SVG view box.
        """
        self._ensure_renderer_updated()

        return self._renderer.viewBoxF()

    def is_valid(self) -> bool:
        """Return whether the current SVG data is valid.

        :return: ``True`` when the current SVG data is valid.
        """
        self._ensure_renderer_updated()

        return self._renderer.isValid()

    def set_fill_color(self, color: Optional[ColorSource]) -> None:
        """Set the replacement color for SVG fill declarations.

        :param color: Fill color to apply.
        """
        self._fill_color = self._normalize_color(color)
        self._is_dirty = True

    def set_themed(self, themed: bool) -> None:
        """Set whether themed replacements are enabled.

        :param themed: Whether themed replacements are enabled.
        """
        if self._themed == themed:
            return

        self._themed = themed
        self._is_dirty = True

    def set_stroke_color(self, color: Optional[ColorSource]) -> None:
        """Set the replacement color for SVG stroke declarations.

        :param color: Stroke color to apply.
        """
        self._stroke_color = self._normalize_color(color)
        self._is_dirty = True

    def set_replacement(
        self,
        search_text: str,
        replacement: ReplacementValue,
    ) -> None:
        """Set a custom text replacement.

        :param search_text: Text to replace in SVG content.
        :param replacement: Replacement value.
        :raises ValueError: If search text is empty.
        """
        if not search_text:
            raise ValueError("Replacement search text must not be empty.")

        self._replacements[search_text] = self._replacement_to_text(
            replacement
        )
        self._is_dirty = True

    def set_replacements(
        self,
        replacements: Mapping[str, ReplacementValue],
    ) -> None:
        """Set multiple custom text replacements.

        :param replacements: Replacement mapping.
        """
        for search_text, replacement in replacements.items():
            self.set_replacement(search_text, replacement)

    def remove_replacement(self, search_text: str) -> None:
        """Remove a custom text replacement.

        :param search_text: Text replacement key to remove.
        """
        if search_text not in self._replacements:
            return

        del self._replacements[search_text]
        self._is_dirty = True

    def clear_replacements(self) -> None:
        """Remove all custom text replacements."""
        if not self._replacements:
            return

        self._replacements.clear()
        self._is_dirty = True

    def original_data(self) -> Optional[QByteArray]:
        """Return the original SVG data before replacements.

        :return: Original SVG data or ``None``.
        """
        if self._original_data is None:
            return None

        return QByteArray(self._original_data)

    def themed_data(self) -> Optional[QByteArray]:
        """Return SVG data after applying current replacements.

        :return: Replaced SVG data or ``None``.
        """
        if self._original_data is None:
            return None

        return self._prepare_svg_data()

    def _ensure_renderer_updated(self) -> None:
        palette_key = self._current_palette_key()

        if not self._is_dirty and palette_key == self._last_palette_key:
            return

        self._reload_renderer()

    def _reload_renderer(self) -> bool:
        if self._original_data is None:
            return False

        themed_data = self._prepare_svg_data()
        is_loaded = self._renderer.load(themed_data)

        self._is_dirty = False
        self._last_palette_key = self._current_palette_key()

        return is_loaded

    def _prepare_svg_data(self) -> QByteArray:
        if self._original_data is None:
            return QByteArray()

        svg_text = bytes(self._original_data).decode("utf-8")

        fill_color = self._resolved_fill_color()
        if fill_color is not None:
            svg_text = self._replace_paint_property(
                svg_text,
                "fill",
                fill_color,
            )

        stroke_color = self._resolved_stroke_color()
        if stroke_color is not None:
            svg_text = self._replace_paint_property(
                svg_text,
                "stroke",
                stroke_color,
            )

        for search_text, replacement in self._replacements.items():
            svg_text = svg_text.replace(search_text, replacement)

        return QByteArray(svg_text.encode("utf-8"))

    def _replace_paint_property(
        self,
        svg_text: str,
        property_name: str,
        color: QColor,
    ) -> str:
        svg_color = self._color_to_svg_text(color)

        attribute_pattern = re.compile(
            rf"(?P<prefix>\b{property_name}\b\s*=\s*)"
            r"(?P<quote>[\"'])"
            r"(?P<value>.*?)"
            r"(?P=quote)",
            flags=re.IGNORECASE,
        )

        style_pattern = re.compile(
            rf"(?P<prefix>(?<![-\w]){property_name}"
            r"(?![-\w])\s*:\s*)"
            r"(?P<value>[^;\"'}]+)",
            flags=re.IGNORECASE,
        )

        svg_text = attribute_pattern.sub(
            lambda match: self._replace_attribute_color(match, svg_color),
            svg_text,
        )

        return style_pattern.sub(
            lambda match: self._replace_style_color(match, svg_color),
            svg_text,
        )

    def _replace_attribute_color(
        self,
        match: re.Match,
        svg_color: str,
    ) -> str:
        value = match.group("value")

        if not self._is_replaceable_color_value(value):
            return match.group(0)

        return (
            f"{match.group('prefix')}"
            f"{match.group('quote')}"
            f"{svg_color}"
            f"{match.group('quote')}"
        )

    def _replace_style_color(self, match: re.Match, svg_color: str) -> str:
        value = match.group("value")
        value_without_important, important_suffix = self._split_important(
            value
        )

        if not self._is_replaceable_color_value(value_without_important):
            return match.group(0)

        return f"{match.group('prefix')}{svg_color}{important_suffix}"

    def _is_replaceable_color_value(self, value: str) -> bool:
        normalized_value = value.strip()
        lowered_value = normalized_value.lower()

        if lowered_value in self._NON_REPLACEABLE_COLORS:
            return False

        if lowered_value.startswith(("url(", "var(")):
            return False

        return QColor(normalized_value).isValid()

    def _split_important(self, value: str) -> tuple:
        stripped_value = value.strip()

        if not stripped_value.lower().endswith("!important"):
            return stripped_value, ""

        return stripped_value[:-10].strip(), " !important"

    def _resolved_fill_color(self) -> Optional[QColor]:
        if self._fill_color is not None:
            return QColor(self._fill_color)

        if not self._themed:
            return None

        return self._theme_text_color()

    def _resolved_stroke_color(self) -> Optional[QColor]:
        if self._stroke_color is not None:
            return QColor(self._stroke_color)

        if not self._themed:
            return None

        return self._theme_text_color()

    def _theme_text_color(self) -> QColor:
        return QgsApplication.palette().text().color()

    def _current_palette_key(self) -> str:
        fill_color = self._resolved_fill_color()
        stroke_color = self._resolved_stroke_color()

        return "|".join(
            (
                fill_color.name() if fill_color is not None else "-",
                str(fill_color.alpha()) if fill_color is not None else "-",
                stroke_color.name() if stroke_color is not None else "-",
                str(stroke_color.alpha()) if stroke_color is not None else "-",
                str(self._themed),
            )
        )

    def _normalize_color(
        self,
        color: Optional[ColorSource],
    ) -> Optional[QColor]:
        if color is None:
            return None

        normalized_color = QColor(color)

        if not normalized_color.isValid():
            raise ValueError(f"Invalid color value: {color!r}")

        return normalized_color

    def _replacement_to_text(self, replacement: ReplacementValue) -> str:
        if isinstance(replacement, QColor):
            return self._color_to_svg_text(replacement)

        try:
            color = QColor(replacement)
        except TypeError:
            return str(replacement)

        if color.isValid() and not isinstance(replacement, str):
            return self._color_to_svg_text(color)

        return str(replacement)

    def _color_to_svg_text(self, color: QColor) -> str:
        return color.name()

    def _read_source(self, source: SvgSource) -> QByteArray:
        if isinstance(source, QByteArray):
            return QByteArray(source)

        if isinstance(source, bytes):
            return QByteArray(source)

        if isinstance(source, Path):
            return self._read_file(str(source))

        if isinstance(source, str):
            return self._read_file(source)

        raise TypeError(f"Unsupported SVG source type: {type(source)!r}")

    def _read_file(self, file_path: str) -> QByteArray:
        svg_file = QFile(file_path)

        if not svg_file.open(QIODevice.OpenModeFlag.ReadOnly):
            raise OSError(
                f"Cannot open SVG file '{file_path}': {svg_file.errorString()}"
            )

        try:
            return svg_file.readAll()
        finally:
            svg_file.close()
