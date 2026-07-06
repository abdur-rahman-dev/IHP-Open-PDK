from copy import deepcopy

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from installer.backend.models import InstallConfig
from installer.frontend.check_page import CheckPage


class ToolCheckWindow(QWidget):
    window_closed = Signal()

    def __init__(self, config: InstallConfig, theme_manager, parent=None):
        super().__init__(parent)
        self.setWindowFlag(Qt.WindowType.Window, True)
        self.setWindowTitle("IHP-Open-PDK Tool Check")
        self.resize(900, 720)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)

        self.check_page = CheckPage(deepcopy(config), theme_manager, self)
        self._build_ui()
        self.check_page.nav_state_changed.connect(self._on_nav_state_changed)
        self.check_page.show_tool_selection()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(8)

        self.header_label = QLabel("Tool Check")
        self.header_label.setObjectName("header_title")
        root.addWidget(self.header_label)
        root.addWidget(self.check_page, 1)

        row = QHBoxLayout()
        row.addStretch()

        self.back_btn = QPushButton("< Back")
        self.back_btn.setFixedWidth(120)
        self.back_btn.clicked.connect(self._on_back_clicked)
        self.back_btn.hide()
        row.addWidget(self.back_btn)

        self.check_btn = QPushButton("Check")
        self.check_btn.setFixedWidth(120)
        self.check_btn.clicked.connect(self._on_check_clicked)
        row.addWidget(self.check_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setFixedWidth(120)
        self.close_btn.clicked.connect(self.close)
        row.addWidget(self.close_btn)

        root.addLayout(row)

    def _on_nav_state_changed(self, state: dict):
        text = state.get("next_text", "")
        enabled = bool(state.get("next_enabled", False))
        if text == "Check":
            self.back_btn.hide()
            self.check_btn.show()
            self.check_btn.setEnabled(enabled)
            return

        self.back_btn.show()
        self.back_btn.setEnabled(True)
        self.check_btn.hide()
        self.check_page.hint_label.setText(
            "Review the tool check results, or go back to change the tool selection."
        )
        self.check_page.hint_label.show()

    def _on_check_clicked(self):
        if self.check_page._tc_phase == "selection":
            self.check_page.run_tool_check()

    def _on_back_clicked(self):
        if self.check_page._tc_phase == "report":
            self.check_page.show_tool_selection(use_defaults=False)

    def closeEvent(self, event: QCloseEvent):
        if self.check_page.tool_worker and self.check_page.tool_worker.isRunning():
            self.check_page.tool_worker.quit()
            self.check_page.tool_worker.wait(1000)
            self.check_page.tool_worker.terminate()
        self.window_closed.emit()
        super().closeEvent(event)
