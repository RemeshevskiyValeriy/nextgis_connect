from pathlib import Path

from qgis.PyQt.QtCore import QCoreApplication, QEvent, Qt
from qgis.PyQt.QtGui import QColor, QImage

from nextgis_connect.ui_kit.widgets.image_preview import (
    ImagePreviewDialog,
    ImagePreviewItem,
)


def _write_png(path: Path, width: int, height: int) -> None:
    image = QImage(width, height, QImage.Format.Format_RGB32)
    image.fill(QColor("#2f6bb2"))

    assert image.save(str(path))


def _delete_dialog(dialog: ImagePreviewDialog) -> None:
    dialog.close()
    dialog.deleteLater()
    QCoreApplication.sendPostedEvents(
        dialog,
        QEvent.Type.DeferredDelete,
    )


def test_image_preview_dialog_has_no_brand_suffix_by_default(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    image_path = tmp_path / "photo.png"
    _write_png(image_path, 12, 8)

    dialog = ImagePreviewDialog(
        [ImagePreviewItem(image_path, image_path.name)],
        0,
    )
    try:
        assert dialog.window_title_suffix == ""
        assert dialog.windowTitle() == "photo.png - 12x8"
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_uses_configured_window_title_suffix(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    image_path = tmp_path / "photo.png"
    _write_png(image_path, 12, 8)

    dialog = ImagePreviewDialog(
        [ImagePreviewItem(image_path, image_path.name)],
        0,
        window_title_suffix="Host Plugin",
    )
    try:
        assert dialog.window_title_suffix == "Host Plugin"
        assert dialog.windowTitle() == "photo.png - 12x8 - Host Plugin"

        dialog.window_title_suffix = ""

        assert dialog.windowTitle() == "photo.png - 12x8"
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_handles_empty_items(qgis_app) -> None:
    del qgis_app

    dialog = ImagePreviewDialog([], 0, window_title_suffix="Host Plugin")
    try:
        assert dialog.windowTitle() == "Image preview - Host Plugin"
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_uses_configured_background(qgis_app) -> None:
    del qgis_app

    dialog = ImagePreviewDialog([ImagePreviewItem(None, "photo.png")], 0)
    try:
        background_color = ImagePreviewDialog.BACKGROUND_COLOR

        assert background_color == "#202326"
        assert dialog.objectName() == "imagePreviewDialog"
        assert background_color in dialog.styleSheet()
        assert background_color in dialog._scroll_area.styleSheet()
        assert background_color in dialog._scroll_area.viewport().styleSheet()
        assert background_color in dialog._image_label.styleSheet()
        assert background_color in dialog._loading_overlay.styleSheet()
        assert background_color not in dialog._panel.styleSheet()
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_counter_fits_two_digit_values(qgis_app) -> None:
    items = [
        ImagePreviewItem(None, f"photo-{index}.png") for index in range(22)
    ]

    dialog = ImagePreviewDialog(items, 0)
    try:
        dialog.show()
        qgis_app.processEvents()

        counter_label = dialog._counter_label
        reserved_text = "22 / 22"

        assert counter_label.text() == "1 / 22"
        assert counter_label.alignment() == Qt.AlignmentFlag.AlignCenter
        assert dialog._previous_button.property("navUnavailable") is True
        assert dialog._next_button.property("navUnavailable") is False
        assert (
            counter_label.fontMetrics().horizontalAdvance(reserved_text)
            <= counter_label.width()
        )
        assert dialog._navigation_widget.width() == (
            dialog._previous_button.width()
            + counter_label.width()
            + dialog._next_button.width()
            + dialog.NAVIGATION_SPACING * 2
        )

        left_gap = (
            counter_label.geometry().left()
            - dialog._previous_button.geometry().right()
            - 1
        )
        right_gap = (
            dialog._next_button.geometry().left()
            - counter_label.geometry().right()
            - 1
        )

        assert left_gap >= dialog.NAVIGATION_SPACING
        assert right_gap >= dialog.NAVIGATION_SPACING
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_boundary_buttons_show_status(qgis_app) -> None:
    del qgis_app

    dialog = ImagePreviewDialog([ImagePreviewItem(None, "photo.png")], 0)
    try:
        assert dialog._previous_button.isEnabled()
        assert dialog._next_button.isEnabled()
        assert dialog._previous_button.property("navUnavailable") is True
        assert dialog._next_button.property("navUnavailable") is True

        dialog._previous_button.click()

        assert dialog._zoom_label_text.text() == "First image"

        dialog._next_button.click()

        assert dialog._zoom_label_text.text() == "Last image"
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_prefetches_adjacent_items(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    requested_indices = []
    items = [
        ImagePreviewItem(tmp_path / f"photo-{index}.png", f"photo-{index}.png")
        for index in range(5)
    ]

    def ensure_item_ready(index: int) -> bool:
        requested_indices.append(index)
        return True

    dialog = ImagePreviewDialog(
        items,
        2,
        ensure_item_ready=ensure_item_ready,
        prefetch_radius=1,
    )
    try:
        assert requested_indices == [2, 3, 1]
        assert dialog._image_ready_check_timer.isActive()
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_loads_file_when_async_request_finishes(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    image_path = tmp_path / "photo.png"

    def ensure_item_ready(index: int) -> bool:
        del index
        return True

    dialog = ImagePreviewDialog(
        [ImagePreviewItem(image_path, image_path.name)],
        0,
        ensure_item_ready=ensure_item_ready,
    )
    try:
        assert dialog._source_pixmap.isNull()

        _write_png(image_path, 12, 8)
        dialog._try_load_current_item()

        assert not dialog._source_pixmap.isNull()
        assert dialog.windowTitle() == "photo.png - 12x8"
        assert not dialog._image_ready_check_timer.isActive()
    finally:
        _delete_dialog(dialog)


def test_image_preview_dialog_keeps_panel_visible_under_cursor(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    dialog = ImagePreviewDialog([ImagePreviewItem(None, "photo.png")], 0)
    try:
        dialog._panel_opacity.setOpacity(dialog.ACTIVE_PANEL_OPACITY)
        monkeypatch.setattr(dialog, "_is_cursor_over_panel", lambda: True)

        dialog._set_idle_panel_opacity()

        assert dialog._panel_opacity.opacity() == dialog.ACTIVE_PANEL_OPACITY
    finally:
        _delete_dialog(dialog)
