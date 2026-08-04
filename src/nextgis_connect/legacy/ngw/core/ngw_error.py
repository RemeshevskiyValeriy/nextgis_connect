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


class NGWError(Exception):
    (
        TypeUnknownError,
        TypeRequestError,
        TypeNGWUnexpectedAnswer,
    ) = list(range(3))  # noqa: RUF012

    def __init__(
        self, type, message, url=None, user_msg=None, need_reconnect=True
    ):
        if not isinstance(message, str):
            self.message = str(message)
        else:
            self.message = message

        self.type = type
        self.url = url
        self.user_msg = user_msg
        self.need_reconnect = need_reconnect

    def __str__(self):
        return self.message
