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

import shutil
import subprocess  # nosec B404
import sys
import time
from pathlib import Path
from typing import Callable, List, TypeVar, Union

PathLike = Union[str, Path]
T = TypeVar("T")

DEFAULT_MAX_TRIES = 5


def _retry_on_permission_error(
    action: Callable[[], T],
    *,
    max_tries: int = DEFAULT_MAX_TRIES,
) -> T:
    for attempt in range(max_tries):
        try:
            return action()
        except PermissionError:
            if attempt + 1 == max_tries:
                raise
            time.sleep(0.1 * 2**attempt)

    raise RuntimeError("Unreachable retry state")


def rm(path: PathLike, *, max_tries: int = DEFAULT_MAX_TRIES) -> None:
    """Remove a file or directory.

    :param path: File or directory path to remove.
    :param max_tries: Maximum number of attempts after permission errors.
    """
    target_path = Path(path)

    def action() -> None:
        if target_path.is_dir():
            shutil.rmtree(str(target_path))
        else:
            target_path.unlink(missing_ok=True)

    _retry_on_permission_error(action, max_tries=max_tries)


def mv(
    from_path: PathLike,
    to_path: PathLike,
    *,
    max_tries: int = DEFAULT_MAX_TRIES,
) -> None:
    """Move a file or directory.

    :param from_path: Source path to move.
    :param to_path: Destination path.
    :param max_tries: Maximum number of attempts after permission errors.
    """
    _retry_on_permission_error(
        lambda: shutil.move(str(from_path), str(to_path)),
        max_tries=max_tries,
    )


def cp(
    from_path: PathLike,
    to_path: PathLike,
    *,
    max_tries: int = DEFAULT_MAX_TRIES,
) -> None:
    """Copy a file or directory.

    :param from_path: Source path to copy.
    :param to_path: Destination path.
    :param max_tries: Maximum number of attempts after permission errors.
    """
    source_path = Path(from_path)
    target_path = Path(to_path)

    def action() -> None:
        if source_path.is_dir():
            shutil.copytree(
                str(source_path),
                str(target_path),
                dirs_exist_ok=True,
            )
        else:
            shutil.copy(str(source_path), str(target_path))

    _retry_on_permission_error(action, max_tries=max_tries)


def reveal_in_file_manager(file_path: Path) -> None:
    """Reveal a file or directory in the system file manager.

    :param file_path: File or directory path to reveal.
    """
    path = file_path.resolve()

    if sys.platform.startswith("win"):
        _reveal_in_windows(path)
        return

    if sys.platform == "darwin":
        _reveal_in_macos(path)
        return

    _reveal_in_linux(path)


def _launch_file_manager(command: List[str]) -> None:
    """Launch a known system file manager command without a shell."""
    subprocess.Popen(command, close_fds=True)  # nosec B603


def _reveal_in_windows(path: Path) -> None:
    # Use Windows Explorer. '/select,' highlights the file in its folder.
    if path.is_dir():
        _launch_file_manager(["explorer", str(path)])
        return

    _launch_file_manager(["explorer", "/select,", str(path)])


def _reveal_in_macos(path: Path) -> None:
    # Use Finder. '-R' reveals the file.
    if path.is_dir():
        _launch_file_manager(["/usr/bin/open", str(path)])
        return

    _launch_file_manager(["/usr/bin/open", "-R", str(path)])


def _reveal_in_linux(path: Path) -> None:
    # TODO: dbus
    _open_base_directory_with_xdg(path)


def _open_base_directory_with_xdg(path: Path) -> None:
    directory = path if path.is_dir() else path.parent
    _launch_file_manager(["xdg-open", str(directory)])
