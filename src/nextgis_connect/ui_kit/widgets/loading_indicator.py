# NextGIS Connect
# Copyright (C) 2026  NextGIS
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or any
# later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, see <https://www.gnu.org/licenses/>.

from typing import Optional

from qgis.PyQt.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QObject,
    QPropertyAnimation,
    QRectF,
    QSize,
    pyqtProperty,
    pyqtSignal,
)
from qgis.PyQt.QtGui import QIcon, QPainter, QPalette
from qgis.PyQt.QtWidgets import QSizePolicy, QWidget

from nextgis_connect.ui_kit.graphics.loading_indicator import (
    LoadingIndicatorRenderer,
)


class LoadingIndicatorAnimation(QObject):
    """Animate an angle property from 0 to 360 degrees indefinitely."""

    ANIMATION_DURATION_MS = 850

    angle_changed = pyqtSignal(float)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        """Initialize the animation object.

        :param parent: Optional QObject parent.
        """
        super().__init__(parent)

        self._angle = 0.0
        self._animation = QPropertyAnimation(self, b"angle", self)
        self._animation.setDuration(self.ANIMATION_DURATION_MS)
        self._animation.setStartValue(0.0)
        self._animation.setEndValue(360.0)
        self._animation.setEasingCurve(QEasingCurve.Type.Linear)
        self._animation.setLoopCount(-1)

    @pyqtProperty(float)
    def angle(self) -> float:
        """Return the current animation angle.

        :return: Current angle in degrees.
        """
        return self._angle

    @angle.setter
    def angle(self, value: float) -> None:
        """Set the current animation angle.

        :param value: Angle in degrees.
        """
        next_angle = value % 360.0
        if self._angle == next_angle:
            return

        self._angle = next_angle
        self.angle_changed.emit(self._angle)

    def start(self) -> None:
        """Start the animation."""
        if self.is_running():
            return

        self._animation.start()

    def stop(self) -> None:
        """Stop the animation and reset its angle."""
        if self.is_running():
            self._animation.stop()

        self.angle = 0.0

    def is_running(self) -> bool:
        """Return whether the animation is running.

        :return: ``True`` when the animation is active.
        """
        return self._animation.state() == QAbstractAnimation.State.Running


class LoadingIndicatorIconAnimator(QObject):
    """Create animated loading icons with a loading indicator renderer."""

    frame_changed = pyqtSignal()

    def __init__(
        self,
        size: Optional[QSize] = None,
        *,
        renderer: Optional[LoadingIndicatorRenderer] = None,
        parent: Optional[QObject] = None,
    ) -> None:
        """Initialize the icon animator.

        :param size: Optional icon size.
        :param renderer: Optional renderer used to draw frames.
        :param parent: Optional QObject parent.
        """
        super().__init__(parent)

        self._size = QSize(size or LoadingIndicatorRenderer.DEFAULT_SIZE)
        self._renderer = renderer or LoadingIndicatorRenderer()
        self._animation = LoadingIndicatorAnimation(self)
        self._animation.angle_changed.connect(
            lambda _angle: self.frame_changed.emit()
        )

    @property
    def angle(self) -> float:
        """Return the current animation angle.

        :return: Current angle in degrees.
        """
        return self._animation.angle

    @angle.setter
    def angle(self, value: float) -> None:
        """Set the current animation angle.

        :param value: Angle in degrees.
        """
        self._animation.angle = value

    def start(self) -> None:
        """Start the icon animation."""
        self._animation.start()
        self.frame_changed.emit()

    def stop(self) -> None:
        """Stop the icon animation."""
        self._animation.stop()
        self.frame_changed.emit()

    def is_running(self) -> bool:
        """Return whether the icon animation is running.

        :return: ``True`` when the animation is active.
        """
        return self._animation.is_running()

    def set_size(self, size: QSize) -> None:
        """Set the rendered icon size.

        :param size: New icon size.
        """
        if not size.isValid() or size.isEmpty():
            return

        if self._size == size:
            return

        self._size = QSize(size)
        self.frame_changed.emit()

    def current_icon(
        self,
        *,
        palette: Optional[QPalette] = None,
        device_pixel_ratio: float = 1.0,
    ) -> QIcon:
        """Return the current animated icon frame.

        :param palette: Optional palette used for rendering.
        :param device_pixel_ratio: Device pixel ratio for the rendered icon.
        :return: Icon for the current animation frame.
        """
        return self._renderer.icon(
            self._size,
            angle=self.angle,
            palette=palette,
            device_pixel_ratio=device_pixel_ratio,
        )


class LoadingIndicatorWidget(QWidget):
    """Provide a reusable spinner widget for long-running operations."""

    DEFAULT_SIZE = QSize(20, 20)

    def __init__(
        self,
        parent: Optional[QWidget] = None,
        *,
        size: Optional[QSize] = None,
        renderer: Optional[LoadingIndicatorRenderer] = None,
    ) -> None:
        """Initialize the loading indicator widget.

        :param parent: Optional parent widget.
        :param size: Optional widget size.
        :param renderer: Optional renderer used to draw the indicator.
        """
        super().__init__(parent)

        self._size = QSize(size or self.DEFAULT_SIZE)
        self._renderer = renderer or LoadingIndicatorRenderer()
        self._animation = LoadingIndicatorAnimation(self)
        self._animation.angle_changed.connect(lambda _angle: self.update())

        self.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )

    @property
    def angle(self) -> float:
        """Return the current animation angle.

        :return: Current angle in degrees.
        """
        return self._animation.angle

    @angle.setter
    def angle(self, value: float) -> None:
        """Set the current animation angle.

        :param value: Angle in degrees.
        """
        self._animation.angle = value

    def start(self) -> None:
        """Start the widget animation."""
        self._animation.start()
        self.update()

    def stop(self) -> None:
        """Stop the widget animation."""
        self._animation.stop()
        self.update()

    def is_running(self) -> bool:
        """Return whether the widget animation is running.

        :return: ``True`` when the animation is active.
        """
        return self._animation.is_running()

    def sizeHint(self) -> QSize:
        """Return the preferred widget size.

        :return: Preferred size.
        """
        return QSize(self._size)

    def minimumSizeHint(self) -> QSize:
        """Return the minimum preferred widget size.

        :return: Minimum preferred size.
        """
        return QSize(self._size)

    def showEvent(self, event) -> None:
        """Handle widget show events.

        :param event: Show event.
        """
        self.start()
        super().showEvent(event)

    def hideEvent(self, event) -> None:
        """Handle widget hide events.

        :param event: Hide event.
        """
        self.stop()
        super().hideEvent(event)

    def paintEvent(self, event) -> None:
        """Paint the current indicator frame.

        :param event: Paint event.
        """
        del event

        painter = QPainter(self)
        self._renderer.paint(
            painter,
            QRectF(self.rect()),
            angle=self.angle,
            palette=self.palette(),
        )
        painter.end()
