from pathlib import Path
from typing import Optional

from qgis.PyQt.QtCore import QEvent, QRectF, QSize, Qt, pyqtSignal
from qgis.PyQt.QtGui import (
    QColor,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
)
from qgis.PyQt.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from nextgis_connect.ui_kit.graphics import (
    NextgisBackgroundPainter,
    NextgisDecorator,
)
from nextgis_connect.ui_kit.graphics.svg_renderer import (
    CustomSvgRenderer,
)


class ClickableLabel(QLabel):
    clicked = pyqtSignal()
    stateChanged = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.__is_hovered = False
        self.__is_pressed = False

    def is_hovered(self) -> bool:
        return self.__is_hovered

    def is_pressed(self) -> bool:
        return self.__is_pressed

    def enterEvent(self, event) -> None:
        self.__is_hovered = True
        self.stateChanged.emit()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.__is_hovered = False
        self.__is_pressed = False
        self.stateChanged.emit()
        super().leaveEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.__is_pressed = True
            self.stateChanged.emit()

        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self.__is_pressed = False
        self.stateChanged.emit()
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

        super().mouseReleaseEvent(event)


class NextgisDialogHeaderWidget(QWidget):
    logoClicked = pyqtSignal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)

        icons_path = Path(__file__).parents[3] / "assets" / "icons"
        self.__background_painter = NextgisBackgroundPainter(
            icons_path / "branding" / "isolines.svg",
            self,
        )
        self.__logo_renderer = CustomSvgRenderer(
            icons_path / "branding" / "nextgis_full_logo.svg",
            self,
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(18)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(4)

        self.__title_label = QLabel(self)
        title_font = self.__title_label.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 2)
        self.__title_label.setFont(title_font)

        self.__subtitle_label = QLabel(self)
        self.__subtitle_label.setWordWrap(True)

        text_layout.addWidget(self.__title_label)
        text_layout.addWidget(self.__subtitle_label)

        self.__logo_label = ClickableLabel(self)
        self.__logo_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.__logo_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.__logo_label.setToolTip(self.tr("Open NextGIS website"))
        self.__logo_label.clicked.connect(self.logoClicked.emit)
        self.__logo_label.stateChanged.connect(self.__sync_logo)

        layout.addLayout(text_layout)
        layout.addStretch(1)
        layout.addWidget(
            self.__logo_label,
            alignment=(
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
            ),
        )

        self.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.setMinimumHeight(92)

        self.__sync_appearance()

    def set_title(self, title: str) -> None:
        self.__title_label.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.__subtitle_label.setVisible(len(subtitle) != 0)
        self.__subtitle_label.setText(subtitle)

    def changeEvent(self, event) -> None:
        if event.type() in (
            QEvent.Type.PaletteChange,
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.StyleChange,
        ):
            self.__sync_appearance()

        super().changeEvent(event)

    def paintEvent(self, event) -> None:
        del event

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(
            self.rect(), self.palette().color(QPalette.ColorRole.Base)
        )
        self.__background_painter.paint_header_background(
            painter,
            self.rect(),
            palette=QPalette(self.palette()),
        )

        border_pen = QPen(self.palette().color(QPalette.ColorRole.Mid))
        painter.setPen(border_pen)
        painter.drawLine(
            self.rect().bottomLeft(),
            self.rect().bottomRight(),
        )

    def __sync_appearance(self) -> None:
        title_palette = QPalette(self.__title_label.palette())
        title_palette.setColor(
            QPalette.ColorRole.WindowText,
            NextgisDecorator.system_title_color(self.palette()),
        )
        self.__title_label.setPalette(title_palette)

        subtitle_palette = QPalette(self.__subtitle_label.palette())
        subtitle_palette.setColor(
            QPalette.ColorRole.WindowText,
            NextgisDecorator.system_muted_text_color(self.palette()),
        )
        self.__subtitle_label.setPalette(subtitle_palette)

        self.__sync_logo()

    def __sync_logo(self) -> None:
        text_color = NextgisDecorator.system_text_color(self.palette())
        self.__logo_renderer.set_replacements(
            {
                "#231F20": text_color,
                "#231f20": text_color,
            }
        )
        self.__logo_label.setPixmap(self.__logo_pixmap(height=24))

    def __logo_pixmap(self, *, height: int) -> QPixmap:
        default_size = self.__logo_renderer.default_size()
        if default_size.isEmpty() or default_size.height() == 0:
            return QPixmap()

        width = max(
            1, int(height * default_size.width() / default_size.height())
        )
        device_pixel_ratio = max(1.0, self.devicePixelRatioF())
        pixmap = QPixmap(
            QSize(
                round(width * device_pixel_ratio),
                round(height * device_pixel_ratio),
            )
        )
        pixmap.setDevicePixelRatio(device_pixel_ratio)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.__logo_renderer.render(
            painter,
            QRectF(0, 0, width, height),
        )
        self.__paint_logo_state_overlay(painter, width, height)
        painter.end()

        return pixmap

    def __paint_logo_state_overlay(
        self,
        painter: QPainter,
        width: int,
        height: int,
    ) -> None:
        if self.__logo_label.is_pressed():
            overlay = QColor(Qt.GlobalColor.black)
            overlay.setAlpha(36)
        elif self.__logo_label.is_hovered():
            overlay = QColor(Qt.GlobalColor.white)
            overlay.setAlpha(34)
        else:
            return

        painter.save()
        painter.setCompositionMode(
            QPainter.CompositionMode.CompositionMode_SourceAtop
        )
        painter.fillRect(QRectF(0, 0, width, height), overlay)
        painter.restore()
