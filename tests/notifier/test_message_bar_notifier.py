from qgis.PyQt.QtWidgets import QHBoxLayout, QPushButton, QWidget

from nextgis_connect.legacy.notifier.message_bar_notifier import (
    MessageBarNotifier,
)
from nextgis_connect.platform.qgis.errors import NgwError


def test_network_error_has_diagnostics_button(qgis_app) -> None:
    del qgis_app

    error = NgwError("Connection error", is_network_problem=True)
    widget = QWidget()
    widget.setLayout(QHBoxLayout())

    notifier = MessageBarNotifier(None)
    notifier._add_error_buttons(error, widget)

    button_texts = [
        button.text() for button in widget.findChildren(QPushButton)
    ]

    assert "Run diagnostics" in button_texts
    assert "Open settings" not in button_texts

    widget.deleteLater()
    notifier.deleteLater()
