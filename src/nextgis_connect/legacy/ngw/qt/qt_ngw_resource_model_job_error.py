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

from typing import Optional

from nextgis_connect.platform.qgis.errors import NgConnectError


class NGWResourceModelJobError(NgConnectError):
    """Common error"""

    def __init__(self, msg, *, user_message=None):
        super().__init__(msg, user_message=user_message)

    @property
    def user_msg(self) -> Optional[str]:
        return self.user_message


class JobError(NGWResourceModelJobError):
    """Specific job error"""

    def __init__(self, msg, wrapped_exception=None):
        super().__init__(msg)
        self.wrapped_exception = wrapped_exception


class JobWarning(NGWResourceModelJobError):
    """Specific job warning"""


class JobServerRequestError(NGWResourceModelJobError):
    """Something wrong with request to NGW like  no connection, 502, ngw error"""

    def __init__(self, msg, url, user_msg=None, need_reconnect=True):
        super().__init__(msg, user_message=user_msg)
        self.url = url
        self.need_reconnect = need_reconnect


class JobNGWError(JobServerRequestError):
    """NGW answer is received, but NGW can't execute request for perform the job"""

    def __init__(self, msg, url):
        super().__init__(msg, url)
