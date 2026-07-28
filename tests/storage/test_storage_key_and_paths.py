from pathlib import Path

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


def test_path_resolver_uses_instance_prefix_hash_and_file_name(
    tmp_path: Path,
) -> None:
    instance_uuid = "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e"
    layer_key = LayerKey(instance_uuid, 42)
    storage_key = StorageKeyFactory.layer_container(layer_key)
    resolver = StoragePathResolver(tmp_path)

    result = resolver.resolve(storage_key, "42.gpkg")

    assert result == (
        tmp_path
        / instance_uuid
        / storage_key.digest[:2]
        / storage_key.digest
        / "42.gpkg"
    )
    assert resolver.relative_to_instance(result, instance_uuid) == Path(
        storage_key.digest[:2],
        storage_key.digest,
        "42.gpkg",
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
