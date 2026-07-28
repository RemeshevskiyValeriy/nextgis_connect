from unittest.mock import Mock

import pytest

from nextgis_connect.platform.filesystem import cp, mv, rm
from nextgis_connect.platform.filesystem.operations import (
    _retry_on_permission_error,
)


def test_rm_removes_files(tmp_path) -> None:
    path = tmp_path / "file.txt"
    path.write_text("content", encoding="utf-8")

    rm(path)

    assert not path.exists()


def test_rm_removes_directories(tmp_path) -> None:
    path = tmp_path / "directory"
    nested_path = path / "nested.txt"
    path.mkdir()
    nested_path.write_text("content", encoding="utf-8")

    rm(path)

    assert not path.exists()


def test_cp_copies_files(tmp_path) -> None:
    source_path = tmp_path / "source.txt"
    target_path = tmp_path / "target.txt"
    source_path.write_text("content", encoding="utf-8")

    cp(source_path, target_path)

    assert source_path.read_text(encoding="utf-8") == "content"
    assert target_path.read_text(encoding="utf-8") == "content"


def test_cp_copies_directories(tmp_path) -> None:
    source_path = tmp_path / "source"
    target_path = tmp_path / "target"
    nested_path = source_path / "nested.txt"
    source_path.mkdir()
    nested_path.write_text("content", encoding="utf-8")

    cp(source_path, target_path)

    assert nested_path.read_text(encoding="utf-8") == "content"
    assert (target_path / "nested.txt").read_text(
        encoding="utf-8"
    ) == "content"


def test_mv_moves_files(tmp_path) -> None:
    source_path = tmp_path / "source.txt"
    target_path = tmp_path / "target.txt"
    source_path.write_text("content", encoding="utf-8")

    mv(source_path, target_path)

    assert not source_path.exists()
    assert target_path.read_text(encoding="utf-8") == "content"


def test_filesystem_retry_uses_exponential_delay(monkeypatch) -> None:
    sleep = Mock()
    action = Mock(side_effect=[PermissionError, PermissionError, None])
    monkeypatch.setattr(
        "nextgis_connect.platform.filesystem.operations.time.sleep",
        sleep,
    )

    _retry_on_permission_error(action)

    assert action.call_count == 3
    sleep.assert_any_call(0.1)
    sleep.assert_any_call(0.2)


def test_filesystem_retry_raises_after_max_tries(monkeypatch) -> None:
    sleep = Mock()
    action = Mock(side_effect=PermissionError)
    monkeypatch.setattr(
        "nextgis_connect.platform.filesystem.operations.time.sleep",
        sleep,
    )

    with pytest.raises(PermissionError):
        _retry_on_permission_error(action, max_tries=3)

    assert action.call_count == 3
    assert sleep.call_count == 2
