import shutil
import time
from pathlib import Path
from typing import Callable, TypeVar, Union

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
