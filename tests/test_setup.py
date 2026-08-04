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

import pytest

from setup import replace_metadata_version


def test_replace_metadata_version_updates_version_line() -> None:
    content = "[general]\nname=NextGIS Connect\nversion = 1.0.0\n"

    assert (
        replace_metadata_version(content, "2.0.0")
        == "[general]\nname=NextGIS Connect\nversion = 2.0.0\n"
    )


def test_replace_metadata_version_requires_version_line() -> None:
    with pytest.raises(RuntimeError, match="metadata version line"):
        replace_metadata_version("[general]\nname=NextGIS Connect\n", "2.0.0")
