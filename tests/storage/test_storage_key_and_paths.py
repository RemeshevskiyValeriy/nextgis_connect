from pathlib import Path

from nextgis_connect.platform.storage.errors import StoragePathError
from nextgis_connect.platform.storage.models import LayerKey
from nextgis_connect.platform.storage.path_resolver import StoragePathResolver
from nextgis_connect.platform.storage.storage_key import StorageKeyFactory


def test_storage_key_is_deterministic() -> None:
    first_key = StorageKeyFactory.layer_container(
        LayerKey("4bdf8332-5df3-4dd4-b9d4-a57d98436b0e", 42)
    )
    second_key = StorageKeyFactory.layer_container(
        LayerKey("4bdf8332-5df3-4dd4-b9d4-a57d98436b0e", 42)
    )

    assert first_key == second_key
    assert len(first_key.digest) == 64


def test_temporary_key_is_namespaced_by_web_gis() -> None:
    first_key = StorageKeyFactory.temporary_file(
        "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e",
        "operation",
        "download",
    )
    second_key = StorageKeyFactory.temporary_file(
        "797e8b8b-59ba-43c5-81af-83bb8d2608f5",
        "operation",
        "download",
    )

    assert first_key != second_key


def test_path_resolver_uses_global_hash_path_and_file_name(
    tmp_path: Path,
) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    layer_key = LayerKey(instance_uuid, 42)
    storage_key = StorageKeyFactory.layer_container(layer_key)
    resolver = StoragePathResolver(tmp_path)
    path_digest = storage_key.digest[: resolver.DIGEST_DIRECTORY_LENGTH]

    result = resolver.resolve(storage_key, "42.gpkg")

    assert result == (tmp_path / path_digest[:2] / path_digest / "42.gpkg")
    assert resolver.relative_to_cache(result) == Path(
        path_digest[:2],
        path_digest,
        "42.gpkg",
    )
    assert resolver.index_path() == tmp_path / "storage.sqlite"


def test_path_resolver_rejects_index_path_outside_cache(
    tmp_path: Path,
) -> None:
    resolver = StoragePathResolver(tmp_path)

    try:
        resolver.absolute_from_entry(Path("..", "outside"))
    except StoragePathError:
        pass
    else:
        raise AssertionError("StoragePathError was not raised")


def test_path_resolver_recognizes_current_and_previous_hash_layouts() -> None:
    for digest_length in (
        StoragePathResolver.DIGEST_DIRECTORY_LENGTH,
        *StoragePathResolver.LEGACY_DIGEST_DIRECTORY_LENGTHS,
    ):
        digest = "a" * digest_length
        path = Path("instance", digest[:2], digest, "42.gpkg")

        assert StoragePathResolver.is_indexed_storage_path(path)

    current_digest = "b" * StoragePathResolver.DIGEST_DIRECTORY_LENGTH
    current_path = Path(
        "instance",
        current_digest[:2],
        current_digest,
        "42.gpkg",
    )
    legacy_digest = "c" * 64
    legacy_path = Path(
        "instance",
        legacy_digest[:2],
        legacy_digest,
        "42.gpkg",
    )

    assert StoragePathResolver.is_indexed_storage_path(
        current_path,
        include_legacy=False,
    )
    assert not StoragePathResolver.is_indexed_storage_path(
        legacy_path,
        include_legacy=False,
    )


def test_attachment_blob_and_preview_keys_use_fileobj_and_blob_key() -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    remote_key = StorageKeyFactory.remote_attachment_blob(
        instance_uuid,
        42,
        777,
    )
    local_key = StorageKeyFactory.local_attachment_blob(
        instance_uuid,
        42,
        "local-blob",
    )
    first_preview_key = StorageKeyFactory.attachment_preview(
        remote_key,
        "small",
    )
    second_preview_key = StorageKeyFactory.attachment_preview(
        local_key,
        "small",
    )

    assert "fileobj:777" in remote_key.seed
    assert "local:local-blob" in local_key.seed
    assert first_preview_key != second_preview_key
    assert remote_key.seed in first_preview_key.seed
