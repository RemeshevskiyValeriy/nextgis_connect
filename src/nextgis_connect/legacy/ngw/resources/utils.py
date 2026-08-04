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
from typing import Sequence


def generate_unique_name(name: str, existing_names: Sequence) -> str:
    if name not in existing_names:
        return name

    if re.search(r"\(\d\)$", name):
        name = name[: name.rfind("(")].rstrip()

    new_name = name.rstrip()
    new_name_with_space = None
    suffix_id = 1
    while new_name in existing_names or new_name_with_space in existing_names:
        new_name = f"{name}({suffix_id})"
        new_name_with_space = f"{name} ({suffix_id})"
        suffix_id += 1

    return new_name if new_name_with_space is None else new_name_with_space
