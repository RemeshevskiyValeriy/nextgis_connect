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
