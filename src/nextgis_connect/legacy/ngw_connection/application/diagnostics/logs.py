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

import logging
from typing import List, cast

from nextgis_connect.platform.logging import logger


class DiagnosticLogHandler(logging.Handler):
    _messages: List[str]

    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self._messages = []
        self.setFormatter(
            logging.Formatter(
                "%(asctime)s     %(levelname)-8s %(message)s",
                datefmt="%Y-%m-%dT%H:%M:%S",
            )
        )

    @property
    def text(self) -> str:
        return "\n".join(self._messages)

    def emit(self, record: logging.LogRecord) -> None:
        self._messages.append(self.format(record))


class DiagnosticLogCapture:
    _handler: DiagnosticLogHandler
    _logger: logging.Logger
    _previous_level: int

    def __init__(self) -> None:
        self._handler = DiagnosticLogHandler()
        self._logger = cast(logging.Logger, logger)
        self._previous_level = self._logger.level

    @property
    def text(self) -> str:
        return self._handler.text

    def __enter__(self) -> "DiagnosticLogCapture":  # noqa: PYI034
        self._previous_level = self._logger.level
        self._logger.setLevel(logging.DEBUG)
        self._logger.addHandler(self._handler)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self._logger.removeHandler(self._handler)
        self._logger.setLevel(self._previous_level)
