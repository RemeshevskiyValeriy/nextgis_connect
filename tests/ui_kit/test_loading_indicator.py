from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QIcon, QPalette

from nextgis_connect.ui_kit.graphics.loading_indicator import (
    LoadingIndicatorRenderer,
)
from nextgis_connect.ui_kit.widgets.loading_indicator import (
    LoadingIndicatorIconAnimator,
    LoadingIndicatorWidget,
)


def _visible_pixel_count(pixmap) -> int:
    image = pixmap.toImage()
    count = 0

    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() > 0:
                count += 1

    return count


def test_loading_indicator_renderer_draws_visible_frame(qgis_app) -> None:
    del qgis_app

    pixmap = LoadingIndicatorRenderer().pixmap(
        QSize(18, 18),
        angle=0.0,
    )

    assert not pixmap.isNull()
    assert _visible_pixel_count(pixmap) > 0


def test_loading_indicator_renderer_rotates_arc(qgis_app) -> None:
    del qgis_app

    renderer = LoadingIndicatorRenderer()
    first_frame = renderer.pixmap(QSize(18, 18), angle=0.0).toImage()
    second_frame = renderer.pixmap(QSize(18, 18), angle=90.0).toImage()

    assert first_frame != second_frame


def test_loading_indicator_renderer_uses_selected_icon_colors(
    qgis_app,
) -> None:
    del qgis_app

    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor("#ffffff"))
    palette.setColor(QPalette.ColorRole.WindowText, QColor("#111111"))
    palette.setColor(QPalette.ColorRole.Highlight, QColor("#0c65af"))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))

    renderer = LoadingIndicatorRenderer()
    icon = renderer.icon(QSize(18, 18), palette=palette)
    normal_frame = icon.pixmap(
        QSize(18, 18),
        QIcon.Mode.Normal,
        QIcon.State.Off,
    ).toImage()
    selected_frame = icon.pixmap(
        QSize(18, 18),
        QIcon.Mode.Selected,
        QIcon.State.Off,
    ).toImage()

    assert renderer._resolved_arc_color(
        palette, selected=True
    ) == palette.color(QPalette.ColorRole.HighlightedText)
    assert normal_frame != selected_frame


def test_loading_indicator_icon_animator_tracks_state(qgis_app) -> None:
    del qgis_app

    animator = LoadingIndicatorIconAnimator(QSize(16, 16))
    animator.angle = 450.0

    assert animator.angle == 90.0
    assert not animator.current_icon().isNull()

    animator.start()
    assert animator.is_running()

    animator.stop()
    assert not animator.is_running()
    assert animator.angle == 0.0


def test_loading_indicator_widget_tracks_state(qgis_app) -> None:
    del qgis_app

    widget = LoadingIndicatorWidget(size=QSize(24, 24))

    assert widget.sizeHint() == QSize(24, 24)
    assert widget.minimumSizeHint() == QSize(24, 24)

    widget.start()
    assert widget.is_running()

    widget.stop()
    assert not widget.is_running()
    widget.deleteLater()
