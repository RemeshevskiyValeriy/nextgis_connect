from pathlib import Path

from nextgis_connect.features.synchronization.infrastructure.storage import (
    AttachmentLifecycle,
    AttachmentStore,
)
from nextgis_connect.platform.storage.models import (
    AttachmentKey,
    AttachmentOperation,
    StorageEntryProtection,
    StorageEntryState,
)


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


def test_restage_uses_unique_path_and_orphans_previous_blob(
    tmp_path: Path,
) -> None:
    first_source_path = tmp_path / "first.txt"
    second_source_path = tmp_path / "second.txt"
    first_source_path.write_text("first", encoding="utf-8")
    second_source_path.write_text("second", encoding="utf-8")
    attachment_store = AttachmentStore(tmp_path)
    attachment_key = _attachment_key()

    first_ref = attachment_store.stage_blob(
        attachment_key,
        first_source_path,
        extension=".txt",
    )
    second_ref = attachment_store.stage_blob(
        attachment_key,
        second_source_path,
        extension=".txt",
    )

    assert first_ref.entry_id is not None
    assert second_ref.entry_id is not None
    assert first_ref.path != second_ref.path
    storage_index = attachment_store.storage_index
    first_entry = storage_index.find_entry_by_id(first_ref.entry_id)
    assert first_entry is not None
    assert first_entry.state == StorageEntryState.ORPHANED
    assert first_entry.protection == StorageEntryProtection.NONE


def test_discard_staged_blob_removes_file_and_record(tmp_path: Path) -> None:
    source_path = tmp_path / "source.txt"
    source_path.write_text("payload", encoding="utf-8")
    attachment_store = AttachmentStore(tmp_path)
    attachment_key = _attachment_key()
    blob_ref = attachment_store.stage_blob(
        attachment_key,
        source_path,
        extension=".txt",
    )
    assert blob_ref.entry_id is not None

    attachment_store.discard_staged_blob(attachment_key)

    storage_index = attachment_store.storage_index
    assert not blob_ref.path.exists()
    assert storage_index.find_entry_by_id(blob_ref.entry_id) is None
    assert storage_index.attachment_record(attachment_key) is None


def test_discard_replacement_restores_committed_blob(tmp_path: Path) -> None:
    replacement_source_path = tmp_path / "replacement.txt"
    replacement_source_path.write_text("replacement", encoding="utf-8")
    attachment_store = AttachmentStore(tmp_path)
    attachment_key = _attachment_key(ngw_aid=42)
    committed_storage_key = attachment_store.remote_blob_key(
        attachment_key.instance_uuid,
        attachment_key.resource_id,
        501,
    )
    committed_path = attachment_store.blob_path(
        committed_storage_key,
        ".txt",
    )
    committed_path.parent.mkdir(parents=True, exist_ok=True)
    committed_path.write_text("committed", encoding="utf-8")
    committed_entry = attachment_store.register_remote_blob(
        attachment_key,
        committed_storage_key,
        committed_path,
        fileobj=501,
        ngw_aid=42,
        extension=".txt",
    )
    assert committed_entry.id is not None
    replacement_ref = attachment_store.stage_blob(
        attachment_key,
        replacement_source_path,
        local_blob_uuid="replacement",
        extension=".txt",
        pending_operation=AttachmentOperation.UPDATE_FILE,
        committed_blob_entry_id=committed_entry.id,
    )

    attachment_store.discard_staged_blob(attachment_key)

    storage_index = attachment_store.storage_index
    record = storage_index.attachment_record(attachment_key)
    assert record is not None
    assert record["committed_blob_entry_id"] == committed_entry.id
    assert record["staged_blob_entry_id"] is None
    assert record["active_blob_entry_id"] == committed_entry.id
    assert record["pending_operation"] == AttachmentOperation.NONE.value
    assert storage_index.find_entry_by_id(replacement_ref.entry_id) is None
    assert committed_path.exists()


def test_register_preview_preserves_pending_operation(tmp_path: Path) -> None:
    source_path = tmp_path / "source.txt"
    source_path.write_text("payload", encoding="utf-8")
    attachment_store = AttachmentStore(tmp_path)
    attachment_key = _attachment_key()
    blob_ref = attachment_store.stage_blob(
        attachment_key,
        source_path,
        local_blob_uuid="preview-source",
        extension=".txt",
    )
    preview_path = attachment_store.preview_path(blob_ref.storage_key)
    preview_path.parent.mkdir(parents=True, exist_ok=True)
    preview_path.write_bytes(b"preview")

    attachment_store.register_preview_file(
        attachment_key,
        blob_ref.storage_key,
    )

    record = attachment_store.storage_index.attachment_record(attachment_key)
    assert record is not None
    assert record["pending_operation"] == AttachmentOperation.CREATE.value
    assert record["staged_blob_entry_id"] == blob_ref.entry_id


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
    storage_index = attachment_store.storage_index
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
