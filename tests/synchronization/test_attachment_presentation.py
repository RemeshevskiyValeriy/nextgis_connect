from pathlib import Path

import pytest
from qgis.PyQt.QtCore import QRect, QRectF, QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPalette, QPixmap
from qgis.PyQt.QtWidgets import QListView, QStyleOptionViewItem

from nextgis_connect.features.synchronization.presentation.attachments import (
    attachment_delegate as attachment_delegate_module,
)
from nextgis_connect.features.synchronization.presentation.attachments.attachment_delegate import (
    AttachmentDelegate,
)
from nextgis_connect.features.synchronization.presentation.attachments.attachment_display_state import (
    AttachmentDisplayState,
)
from nextgis_connect.features.synchronization.presentation.attachments.attachment_icon_painter import (
    AttachmentIconPainter,
)
from nextgis_connect.features.synchronization.presentation.attachments.attachment_icon_provider import (
    AttachmentIconProvider,
)
from nextgis_connect.legacy.detached_editing.identification.attachments_model import (
    AttachmentLoadingKind,
    AttachmentsModel,
)
from nextgis_connect.legacy.detached_editing.utils import AttachmentMetadata
from nextgis_connect.ui_kit.icons import material_icon_path


def _visible_pixel_count(pixmap: QPixmap) -> int:
    image = pixmap.toImage()
    count = 0

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                count += 1

    return count


def _render_download_icon_image(
    icon_name: str,
    logical_size: int,
    *,
    device_pixel_ratio: float = 1.0,
):
    physical_size = round(logical_size * device_pixel_ratio)
    pixmap = QPixmap(physical_size, physical_size)
    pixmap.setDevicePixelRatio(device_pixel_ratio)
    pixmap.fill(Qt.GlobalColor.transparent)

    icon_painter = AttachmentIconPainter(QSize(logical_size, logical_size))
    painter = QPainter(pixmap)
    icon_painter._paint_download_icon(
        painter,
        icon_name,
        QRectF(0.0, 0.0, float(logical_size), float(logical_size)),
    )
    painter.end()

    return pixmap.toImage()


class _LoadingRendererProbe:
    def __init__(self):
        self.calls = []

    def paint(self, painter, rect, **kwargs):
        del painter
        del rect
        self.calls.append(kwargs)


class _PainterPlaceholderProbe:
    def __init__(self):
        self.draw_text_calls = []

    def drawText(self, *args):
        self.draw_text_calls.append(args)


def test_attachment_icon_provider_uses_known_extension() -> None:
    provider = AttachmentIconProvider()

    assert (
        provider.icon_path_for_file_name("REPORT.PDF") == "attachments/pdf.svg"
    )


def test_attachment_icon_provider_falls_back_to_unknown() -> None:
    provider = AttachmentIconProvider()

    assert (
        provider.icon_path_for_file_name("archive.unknown-extension")
        == "attachments/unknown.svg"
    )
    assert (
        provider.icon_path_for_file_name("README") == "attachments/unknown.svg"
    )
    assert provider.icon_path_for_file_name(None) == "attachments/unknown.svg"


def test_attachments_model_exposes_loading_display_state(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    attachment_path = tmp_path / "report.pdf"
    attachment_path.write_bytes(b"PDF")
    attachment = AttachmentMetadata(
        fid=1,
        aid=2,
        name="report.pdf",
        description="Description",
        mime_type="application/pdf",
        file_path=attachment_path,
    )
    model = AttachmentsModel([attachment])
    index = model.index(0)

    state = AttachmentDisplayState.from_index(index)
    editor_state = AttachmentDisplayState.from_index(index, for_editor=True)

    assert state.title.startswith("report.pdf")
    assert editor_state.title == "report.pdf"
    assert state.description == "Description"
    assert state.mime_type == "application/pdf"
    assert state.attachment_identity == (1, 2)
    assert state.is_cached
    assert not state.is_loading
    assert state.loading_progress is None
    assert state.loading_kind == ""

    model.set_attachment_loading_progress(2, 125.0)
    state = AttachmentDisplayState.from_index(index)

    assert state.is_loading
    assert state.loading_progress == 100.0
    assert state.loading_kind == AttachmentLoadingKind.FILE.value
    assert isinstance(state.icon_value, QIcon)

    model.set_attachment_loading_progress(2, None)
    state = AttachmentDisplayState.from_index(index)

    assert not state.is_loading
    assert state.loading_progress is None
    assert state.loading_kind == ""


def test_attachments_model_exposes_preview_loading_kind(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    attachment_path = tmp_path / "photo.jpg"
    attachment = AttachmentMetadata(
        fid=1,
        aid=2,
        name="photo.jpg",
        description="",
        mime_type="image/jpeg",
        file_path=attachment_path,
    )
    model = AttachmentsModel([attachment])

    model.set_attachment_loading_progress(
        2,
        50.0,
        AttachmentLoadingKind.PREVIEW,
    )
    state = AttachmentDisplayState.from_index(model.index(0))

    assert state.is_loading
    assert state.loading_progress == 50.0
    assert state.loading_kind == AttachmentLoadingKind.PREVIEW.value
    assert state.is_preview_loading
    assert state.icon_value is None


def test_attachments_model_keeps_cache_state_stable_while_loading(
    qgis_app,
    tmp_path: Path,
) -> None:
    del qgis_app

    attachment_path = tmp_path / "report.pdf"
    attachment = AttachmentMetadata(
        fid=1,
        aid=2,
        name="report.pdf",
        description="",
        mime_type="application/pdf",
        file_path=attachment_path,
    )
    model = AttachmentsModel([attachment])
    index = model.index(0)

    model.set_attachment_loading_progress(2, 100.0)
    attachment_path.write_bytes(b"PDF")
    model.update_cached_states()
    state = AttachmentDisplayState.from_index(index)

    assert state.is_loading
    assert not state.is_cached

    model.set_attachment_loading_progress(2, None)
    model.update_cached_states()
    state = AttachmentDisplayState.from_index(index)

    assert not state.is_loading
    assert state.is_cached


def test_attachment_icon_painter_arc_length_follows_progress() -> None:
    painter = AttachmentIconPainter(QSize(48, 48))
    overlay_rect = QRect(0, 0, 24, 24)

    assert painter._loading_indicator_pen_width(overlay_rect) == pytest.approx(
        24.0
        / AttachmentIconPainter.LOADING_INDICATOR_SOURCE_SIZE
        * AttachmentIconPainter.LOADING_INDICATOR_SOURCE_PEN_WIDTH
    )
    assert painter._arc_degrees(None) is None
    assert painter._arc_degrees(0.0) == 12.0
    assert painter._arc_degrees(50.0) == 180.0
    assert painter._arc_degrees(100.0) == 360.0


def test_attachment_icon_painter_uses_configured_loading_track() -> None:
    painter = AttachmentIconPainter(QSize(48, 48))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#ff5500"))

    track_color = painter._loading_renderer._resolved_track_color(
        palette, selected=True
    )

    assert track_color == AttachmentIconPainter.LOADING_TRACK_COLOR
    assert painter._loading_renderer._resolved_arc_color(
        palette, selected=True
    ) == palette.color(QPalette.ColorRole.Highlight)


def test_attachment_icon_painter_resolves_loading_download_icon() -> None:
    icon_path = material_icon_path(
        AttachmentIconPainter.LOADING_DOWNLOAD_ICON_NAME
    )

    assert icon_path is not None
    assert icon_path.name.startswith("download_for_offline_arrow_")


def test_loading_download_icon_renders_without_outer_ring(qgis_app) -> None:
    del qgis_app

    full_image = _render_download_icon_image(
        AttachmentIconPainter.DOWNLOAD_ICON_NAME,
        48,
    )
    loading_image = _render_download_icon_image(
        AttachmentIconPainter.LOADING_DOWNLOAD_ICON_NAME,
        48,
    )

    assert full_image.pixelColor(4, 24).alpha() > 0
    assert loading_image.pixelColor(4, 24).alpha() == 0


def test_loading_download_icon_renders_without_outer_ring_on_high_dpi(
    qgis_app,
) -> None:
    del qgis_app

    for device_pixel_ratio in (1.0, 2.0, 3.0):
        image = _render_download_icon_image(
            AttachmentIconPainter.LOADING_DOWNLOAD_ICON_NAME,
            28,
            device_pixel_ratio=device_pixel_ratio,
        )
        ring_x = round(28.0 * 4.0 / 48.0 * device_pixel_ratio)
        center_y = round(14.0 * device_pixel_ratio)

        assert image.pixelColor(ring_x, center_y).alpha() == 0


def test_attachment_icon_painter_grays_white_uncached_icon(qgis_app) -> None:
    del qgis_app

    source = QPixmap(16, 16)
    source.fill(Qt.GlobalColor.transparent)
    painter = QPainter(source)
    painter.fillRect(4, 4, 8, 8, QColor("#ffffff"))
    painter.end()

    result = AttachmentIconPainter(QSize(16, 16))._disabled_pixmap(source)
    image = result.toImage()
    center_color = image.pixelColor(8, 8)
    corner_color = image.pixelColor(0, 0)

    assert center_color.alpha() == 255
    assert center_color != QColor("#ffffff")
    assert center_color.red() == center_color.green() == center_color.blue()
    assert corner_color.alpha() == 0


def test_attachment_icon_painter_darkens_uncached_preview(qgis_app) -> None:
    del qgis_app

    source = QPixmap(2, 1)
    source.fill(QColor("#ffffff"))
    painter = QPainter(source)
    painter.fillRect(1, 0, 1, 1, QColor("#202020"))
    painter.end()

    result = AttachmentIconPainter(QSize(2, 1))._dimmed_pixmap(source)
    image = result.toImage()
    light_color = image.pixelColor(0, 0)
    dark_color = image.pixelColor(1, 0)

    assert light_color.red() < 255
    assert light_color.green() < 255
    assert light_color.blue() < 255
    assert dark_color.red() < 32
    assert dark_color.green() < 32
    assert dark_color.blue() < 32


def test_attachment_icon_painter_can_delay_loading_progress() -> None:
    painter = AttachmentIconPainter(QSize(16, 16))
    calls = []
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=True,
        loading_progress=25.0,
    )

    painter._paint_base_icon = lambda *args: calls.append("base")
    painter._paint_loading_overlay = (
        lambda _painter, _rect, progress, **kwargs: calls.append(
            ("loading", progress)
        )
    )
    painter._paint_download_overlay = lambda *args, **kwargs: calls.append(
        (
            "download",
            kwargs.get(
                "icon_name",
                AttachmentIconPainter.DOWNLOAD_ICON_NAME,
            ),
        )
    )

    painter.paint(
        QPainter(),
        QPixmap(16, 16).rect(),
        state,
        palette=QPalette(),
        selected=False,
        show_loading_progress=False,
    )

    assert calls == [
        "base",
        ("download", AttachmentIconPainter.LOADING_DOWNLOAD_ICON_NAME),
        ("loading", None),
    ]


def test_attachment_icon_painter_preview_loading_draws_only_indicator() -> (
    None
):
    painter = AttachmentIconPainter(QSize(16, 16))
    calls = []
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=True,
        loading_progress=25.0,
        loading_kind=AttachmentLoadingKind.PREVIEW.value,
    )

    painter._paint_base_icon = lambda *args: calls.append("base")
    painter._paint_loading_background = lambda *args: calls.append(
        "background"
    )
    painter._paint_loading_overlay = (
        lambda _painter, _rect, progress, **kwargs: calls.append(
            ("loading", progress)
        )
    )
    painter._paint_download_overlay = lambda *args, **kwargs: calls.append(
        "download"
    )

    painter.paint(
        QPainter(),
        QPixmap(16, 16).rect(),
        state,
        palette=QPalette(),
        selected=False,
    )

    assert calls == ["background", ("loading", 25.0)]


def test_attachment_delegate_omits_placeholder_for_loading_icon(
    qgis_app,
) -> None:
    del qgis_app

    view = QListView()
    delegate = AttachmentDelegate(view)
    painter = _PainterPlaceholderProbe()
    option = QStyleOptionViewItem()
    option.rect = QRect(0, 0, 240, 64)
    option.font = view.font()
    option.palette = view.palette()
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=True,
        loading_progress=25.0,
        loading_kind=AttachmentLoadingKind.PREVIEW.value,
    )
    layout = delegate._compute_layout(
        option,
        state.icon_value,
        state.title,
        state.description,
    )
    delegate._icon_painter.paint = lambda *args, **kwargs: None

    try:
        delegate._draw_icon(painter, option, state, layout)

        assert painter.draw_text_calls == []
    finally:
        view.close()
        view.deleteLater()


def test_attachment_icon_painter_keeps_loading_icon_at_full_progress() -> None:
    painter = AttachmentIconPainter(QSize(16, 16))
    calls = []
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=True,
        loading_progress=100.0,
    )

    painter._paint_base_icon = lambda *args: calls.append("base")
    painter._paint_loading_overlay = (
        lambda _painter, _rect, progress, **kwargs: calls.append(
            ("loading", progress)
        )
    )
    painter._paint_download_overlay = lambda *args, **kwargs: calls.append(
        (
            "download",
            kwargs.get(
                "icon_name",
                AttachmentIconPainter.DOWNLOAD_ICON_NAME,
            ),
        )
    )

    painter.paint(
        QPainter(),
        QPixmap(16, 16).rect(),
        state,
        palette=QPalette(),
        selected=False,
    )

    assert calls == [
        "base",
        ("download", AttachmentIconPainter.LOADING_DOWNLOAD_ICON_NAME),
        ("loading", 100.0),
    ]


def test_attachment_icon_painter_keeps_loading_icon_when_cached() -> None:
    painter = AttachmentIconPainter(QSize(16, 16))
    calls = []
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=True,
        is_loading=True,
        loading_progress=100.0,
    )

    painter._paint_base_icon = lambda *args: calls.append("base")
    painter._paint_loading_overlay = (
        lambda _painter, _rect, progress, **kwargs: calls.append(
            ("loading", progress)
        )
    )
    painter._paint_download_overlay = lambda *args, **kwargs: calls.append(
        (
            "download",
            kwargs.get(
                "icon_name",
                AttachmentIconPainter.DOWNLOAD_ICON_NAME,
            ),
        )
    )

    painter.paint(
        QPainter(),
        QPixmap(16, 16).rect(),
        state,
        palette=QPalette(),
        selected=False,
    )

    assert calls == [
        "base",
        ("download", AttachmentIconPainter.LOADING_DOWNLOAD_ICON_NAME),
        ("loading", 100.0),
    ]


def test_attachment_icon_painter_uses_full_download_icon_when_idle() -> None:
    painter = AttachmentIconPainter(QSize(16, 16))
    calls = []
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=False,
        loading_progress=None,
    )

    painter._paint_base_icon = lambda *args: calls.append("base")
    painter._paint_download_overlay = lambda *args, **kwargs: calls.append(
        (
            "download",
            kwargs.get(
                "icon_name",
                AttachmentIconPainter.DOWNLOAD_ICON_NAME,
            ),
        )
    )
    painter._paint_loading_overlay = (
        lambda _painter, _rect, progress, **kwargs: calls.append(
            ("loading", progress)
        )
    )

    painter.paint(
        QPainter(),
        QPixmap(16, 16).rect(),
        state,
        palette=QPalette(),
        selected=False,
    )

    assert calls == [
        "base",
        ("download", AttachmentIconPainter.DOWNLOAD_ICON_NAME),
    ]


def test_attachment_icon_painter_loading_overlay_has_no_inner_fill(
    qgis_app,
) -> None:
    del qgis_app

    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    icon_painter = AttachmentIconPainter(QSize(48, 48))
    icon_painter._paint_loading_overlay(
        painter,
        QRect(0, 0, 48, 48),
        None,
        palette=QPalette(),
        selected=False,
        angle=0.0,
    )
    painter.end()

    image = pixmap.toImage()
    overlay_rect = icon_painter._overlay_rect(QRect(0, 0, 48, 48))
    indicator_rect = icon_painter._loading_indicator_rect(overlay_rect)

    expected_overlay_size = max(
        AttachmentIconPainter.DOWNLOAD_ICON_MIN_SIZE,
        24,
    )

    assert overlay_rect.size() == QSize(
        expected_overlay_size,
        expected_overlay_size,
    )
    expected_inset = (
        AttachmentIconPainter.LOADING_INDICATOR_SOURCE_INSET
        * expected_overlay_size
        / AttachmentIconPainter.LOADING_INDICATOR_SOURCE_SIZE
    )
    assert indicator_rect.left() == pytest.approx(
        overlay_rect.left() + expected_inset
    )
    assert indicator_rect.top() == pytest.approx(
        overlay_rect.top() + expected_inset
    )
    assert indicator_rect.width() == pytest.approx(
        overlay_rect.width() - expected_inset * 2.0
    )
    assert indicator_rect.height() == pytest.approx(
        overlay_rect.height() - expected_inset * 2.0
    )
    assert image.pixelColor(24, 24).alpha() == 0


def test_attachment_icon_painter_progress_arc_keeps_rotating(
    qgis_app,
) -> None:
    del qgis_app

    loading_renderer = _LoadingRendererProbe()
    icon_painter = AttachmentIconPainter(
        QSize(16, 16),
        loading_renderer=loading_renderer,
    )
    pixmap = QPixmap(16, 16)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)

    icon_painter._paint_loading_overlay(
        painter,
        QRect(0, 0, 16, 16),
        50.0,
        palette=QPalette(),
        selected=False,
        angle=123.0,
    )
    icon_painter._paint_loading_overlay(
        painter,
        QRect(0, 0, 16, 16),
        None,
        palette=QPalette(),
        selected=False,
        angle=123.0,
    )
    painter.end()

    assert loading_renderer.calls[0]["angle"] == 123.0
    assert loading_renderer.calls[0]["arc_degrees"] == 180.0
    assert loading_renderer.calls[1]["angle"] == 123.0
    assert loading_renderer.calls[1]["arc_degrees"] is None


def test_attachment_icon_painter_scales_loading_geometry() -> None:
    painter = AttachmentIconPainter(QSize(64, 64))
    overlay_rect = QRect(0, 0, 32, 32)
    indicator_rect = painter._loading_indicator_rect(overlay_rect)

    assert painter._loading_indicator_pen_width(overlay_rect) == pytest.approx(
        32.0
        / AttachmentIconPainter.LOADING_INDICATOR_SOURCE_SIZE
        * AttachmentIconPainter.LOADING_INDICATOR_SOURCE_PEN_WIDTH
    )
    assert indicator_rect.left() == pytest.approx(
        32.0
        / AttachmentIconPainter.LOADING_INDICATOR_SOURCE_SIZE
        * AttachmentIconPainter.LOADING_INDICATOR_SOURCE_INSET
    )
    assert indicator_rect.top() == pytest.approx(
        32.0
        / AttachmentIconPainter.LOADING_INDICATOR_SOURCE_SIZE
        * AttachmentIconPainter.LOADING_INDICATOR_SOURCE_INSET
    )
    assert indicator_rect.width() == pytest.approx(32.0 - 32.0 / 48.0 * 8.0)
    assert indicator_rect.height() == pytest.approx(32.0 - 32.0 / 48.0 * 8.0)


def test_attachment_icon_painter_loading_overlay_scales_on_high_dpi(
    qgis_app,
) -> None:
    del qgis_app

    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=True,
        loading_progress=50.0,
    )

    for device_pixel_ratio in (1.0, 2.0, 3.0):
        physical_size = round(48.0 * device_pixel_ratio)
        pixmap = QPixmap(physical_size, physical_size)
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        AttachmentIconPainter(QSize(48, 48)).paint(
            painter,
            QRect(0, 0, 48, 48),
            state,
            palette=QPalette(),
            selected=False,
            loading_angle=0.0,
        )
        painter.end()

        image = pixmap.toImage()

        assert image.width() == physical_size
        assert image.height() == physical_size
        assert image.pixelColor(0, 0).alpha() == 0
        assert _visible_pixel_count(pixmap) > 0


def test_attachment_delegate_delays_loading_progress(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    current_time = 100.0
    monkeypatch.setattr(
        attachment_delegate_module.time,
        "monotonic",
        lambda: current_time,
    )

    view = QListView()
    delegate = AttachmentDelegate(view)
    state = AttachmentDisplayState(
        icon_value=None,
        attachment_identity=(1, 2),
        title="",
        description="",
        mime_type="",
        is_cached=False,
        is_loading=True,
        loading_progress=25.0,
    )
    try:
        assert not delegate._is_loading_progress_visible(state)

        current_time = 100.249

        assert not delegate._is_loading_progress_visible(state)

        current_time = 100.251

        assert delegate._is_loading_progress_visible(state)
    finally:
        view.close()
        view.deleteLater()


def test_attachment_delegate_animates_without_progress_changes(
    qgis_app,
    monkeypatch,
) -> None:
    del qgis_app

    current_time = 100.0
    monkeypatch.setattr(
        attachment_delegate_module.time,
        "monotonic",
        lambda: current_time,
    )

    view = QListView()
    delegate = AttachmentDelegate(view)
    delegate._has_loading_items = lambda: True
    delegate._loading_last_frame_time = current_time

    try:
        current_time = 100.05
        delegate._advance_loading_animation()

        assert delegate._loading_angle == pytest.approx(12.0)
    finally:
        view.close()
        view.deleteLater()
