from pathlib import Path

from nextgis_connect.features.synchronization.infrastructure.storage import (
    AttachmentLifecycle,
    AttachmentStore,
)
from nextgis_connect.platform.storage.models import AttachmentKey


def test_stage_blob_uses_local_blob_uuid(tmp_path: Path) -> None:
    source_path = tmp_path / "source.txt"
    source_path.write_text("payload", encoding="utf-8")
    attachment_store = AttachmentStore(tmp_path)
    attachment_key = _attachment_key()

    blob_ref = attachment_store.stage_blob(
        attachment_key,
        source_path,
        local_blob_uuid="local-blob-1",
        extension=".txt",
    )

    assert "local:local-blob-1" in blob_ref.storage_key.seed
    assert blob_ref.path.name == "blob.txt"


def test_remote_blob_path_uses_fileobj(tmp_path: Path) -> None:
    attachment_store = AttachmentStore(tmp_path)
    storage_key = attachment_store.remote_blob_key(
        "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e",
        42,
        501,
    )

    assert "fileobj:501" in storage_key.seed
    assert attachment_store.blob_path(storage_key).name == "blob"


def test_preview_path_depends_on_blob_key_not_aid(tmp_path: Path) -> None:
    attachment_store = AttachmentStore(tmp_path)
    first_blob_key = attachment_store.remote_blob_key(
        "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e",
        42,
        501,
    )
    second_blob_key = attachment_store.remote_blob_key(
        "4bdf8332-5df3-4dd4-b9d4-a57d98436b0e",
        42,
        502,
    )

    assert attachment_store.preview_path(first_blob_key) != (
        attachment_store.preview_path(second_blob_key)
    )


def test_replacement_keeps_committed_blob_and_creates_staged_blob(
    tmp_path: Path,
) -> None:
    first_source_path = tmp_path / "first.txt"
    second_source_path = tmp_path / "second.txt"
    first_source_path.write_text("first", encoding="utf-8")
    second_source_path.write_text("second", encoding="utf-8")
    attachment_store = AttachmentStore(tmp_path)
    lifecycle = AttachmentLifecycle(attachment_store)
    attachment_key = _attachment_key(ngw_aid=42)
    committed_ref = lifecycle.stage_new_file(
        attachment_key,
        first_source_path,
        local_blob_uuid="committed-local",
        extension=".txt",
    )
    assert committed_ref.entry_id is not None

    staged_ref = lifecycle.stage_replacement(
        attachment_key,
        second_source_path,
        committed_blob_entry_id=committed_ref.entry_id,
        local_blob_uuid="replacement-local",
        extension=".txt",
    )
    storage_index = attachment_store.index_for_instance(
        attachment_key.instance_uuid
    )
    record = storage_index.attachment_record(attachment_key)

    assert record is not None
    assert record["committed_blob_entry_id"] == committed_ref.entry_id
    assert record["staged_blob_entry_id"] == staged_ref.entry_id
    assert record["active_blob_entry_id"] == staged_ref.entry_id


def _attachment_key(ngw_aid=None) -> AttachmentKey:
    return AttachmentKey(
        instance_uuid="4bdf8332-5df3-4dd4-b9d4-a57d98436b0e",
        resource_id=42,
        feature_local_id=1,
        feature_ngw_fid=None,
        local_attachment_id="local-attachment",
        ngw_aid=ngw_aid,
    )
