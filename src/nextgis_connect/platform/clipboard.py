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

import platform
from typing import Union

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QByteArray, QMimeData
from qgis.PyQt.QtGui import QClipboard, QImage, QPixmap

ClipboardBytes = Union[QByteArray, bytes, bytearray]
ClipboardImage = Union[QImage, QPixmap]


class Clipboard:
    """Provide application clipboard operations."""

    def set_data(
        self,
        mime_type: str,
        data: ClipboardBytes,
        text: str = "",
    ) -> None:
        """Set arbitrary MIME data on the application clipboard."""
        mime_data = QMimeData()
        mime_data.setData(mime_type, data)
        if text:
            mime_data.setText(text)
        self._set_mime_data(mime_data)

    def copy_image(self, image: ClipboardImage) -> None:
        """Copy image content to the application clipboard."""
        clipboard_image = self._image_to_qimage(image)
        if clipboard_image.isNull():
            return

        clipboard = self._clipboard()
        if platform.system() == "Linux":
            clipboard.setImage(
                clipboard_image,
                QClipboard.Mode.Selection,
            )
        clipboard.setImage(clipboard_image, QClipboard.Mode.Clipboard)

    def _set_mime_data(self, mime_data: QMimeData) -> None:
        clipboard = self._clipboard()
        if platform.system() == "Linux":
            clipboard.setMimeData(
                self._clone_mime_data(mime_data),
                QClipboard.Mode.Selection,
            )
        clipboard.setMimeData(mime_data, QClipboard.Mode.Clipboard)

    def _clipboard(self) -> QClipboard:
        clipboard = QgsApplication.clipboard()
        assert clipboard is not None
        return clipboard

    def _clone_mime_data(self, mime_data: QMimeData) -> QMimeData:
        clone = QMimeData()
        for mime_type in mime_data.formats():
            clone.setData(mime_type, mime_data.data(mime_type))
        if mime_data.hasText():
            clone.setText(mime_data.text())
        if mime_data.hasUrls():
            clone.setUrls(mime_data.urls())
        return clone

    def _image_to_qimage(self, image: ClipboardImage) -> QImage:
        if isinstance(image, QPixmap):
            return image.toImage()

        return image
