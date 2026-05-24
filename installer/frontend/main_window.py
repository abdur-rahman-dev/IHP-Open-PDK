import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QMessageBox, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QCloseEvent

from installer.backend.models import InstallConfig
from installer.frontend.choice_page import ChoicePage
from installer.frontend.check_page import CheckPage


class MainWindow(QMainWindow):
    def __init__(self, theme_manager):
        super().__init__()
        self.config = InstallConfig()
        self.theme_manager = theme_manager

        script_dir = Path(__file__).resolve().parent
        for candidate in [script_dir, script_dir.parent]:
            if candidate.name == "installer":
                candidate = candidate.parent
            for child in candidate.iterdir():
                if child.is_dir() and (child / "libs.tech").is_dir():
                    self.config.pdk_root = str(candidate)
                    break

        env_pdk_root = os.environ.get("PDK_ROOT")
        env_pdk = os.environ.get("PDK")
        auto_change = bool(env_pdk_root and env_pdk)

        self._build_ui()

        if auto_change:
            self.choice_page.mode_change.setChecked(True)
            self.choice_page.mode_new.setChecked(False)

        default_pdk_dir = ""
        if env_pdk_root and env_pdk:
            default_pdk_dir = os.path.join(env_pdk_root, env_pdk)
        elif self.config.pdk_root:
            default_pdk_dir = os.path.join(
                self.config.pdk_root, self.config.pdk.value
            )
        if default_pdk_dir:
            self.choice_page.dir_input.setText(default_pdk_dir)

    def _build_ui(self):
        self.setWindowTitle("IHP-Open-PDK Installer")
        self.setMinimumSize(720, 620)
        self.resize(800, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)

        header_row = QHBoxLayout()

        header_spacer = QLabel("")
        header_spacer.setFixedWidth(108)
        header_row.addWidget(header_spacer)

        self.header_label = QLabel("Configuration")
        self.header_label.setFont(QFont("Sans", 16, QFont.Bold))
        self.header_label.setObjectName("header_title")
        self.header_label.setAlignment(Qt.AlignCenter)
        header_row.addWidget(self.header_label, 1)

        self.theme_combo = self.theme_manager.create_combo(self)
        self.theme_combo.setFixedWidth(108)
        header_row.addWidget(self.theme_combo)

        root.addLayout(header_row)

        sep = QLabel("")
        sep.setFixedHeight(2)
        sep.setObjectName("separator")
        root.addWidget(sep)

        self.stacked = QStackedWidget()
        root.addWidget(self.stacked, 1)

        self.choice_page = ChoicePage(self.config)
        self.check_page = CheckPage(self.config, self.theme_manager)

        self.stacked.addWidget(self.choice_page)
        self.stacked.addWidget(self.check_page)

        nav_lay = QHBoxLayout()
        nav_lay.addStretch()

        self.step_label = QLabel("Step 1 of 2: Configuration")
        self.step_label.setObjectName("step_label")
        self.step_label.setAlignment(Qt.AlignCenter)
        nav_lay.addWidget(self.step_label)
        nav_lay.addStretch()

        self.back_btn = QPushButton("< Back")
        self.back_btn.setFixedWidth(100)
        self.back_btn.clicked.connect(self._go_to_choices)
        self.back_btn.hide()
        nav_lay.addWidget(self.back_btn)

        self.next_btn = QPushButton("Next >")
        self.next_btn.setFixedWidth(120)
        self.next_btn.clicked.connect(self._on_next_action)
        nav_lay.addWidget(self.next_btn)

        self.close_btn = QPushButton("Close")
        self.close_btn.setFixedWidth(80)
        self.close_btn.setObjectName("close_btn")
        self.close_btn.clicked.connect(self.close)
        nav_lay.addWidget(self.close_btn)

        root.addLayout(nav_lay)

        self.check_page.install_ready.connect(self._on_install_ready)
        self.check_page.back_allowed.connect(self._on_back_allowed)

        self._update_nav()

    def _update_nav(self):
        idx = self.stacked.currentIndex()
        total = self.stacked.count()
        step_name = self._step_name(idx)
        self.step_label.setText(f"Step {idx + 1} of {total}: {step_name}")
        self.header_label.setText(step_name)

        if idx == 0:
            self.back_btn.hide()
            self.next_btn.setText("Next >")
            self.next_btn.setObjectName("")
            self.next_btn.setEnabled(True)
            self.next_btn.setStyle(self.next_btn.style())
        elif idx == 1:
            self.back_btn.show()
            self.back_btn.setEnabled(True)
            self.next_btn.setText("Install")
            self.next_btn.setObjectName("install_btn")
            self.next_btn.setStyle(self.next_btn.style())
            self.next_btn.setEnabled(False)

    def _step_name(self, idx):
        return ["Configuration", "Check & Install"][idx]

    def _on_next(self):
        if self.stacked.currentIndex() == 0:
            config = self.choice_page.get_config()
            missing = []
            if not config.simulators:
                missing.append("simulator")
            if not config.schematic_editors:
                missing.append("schematic editor")
            if not config.layout_editors:
                missing.append("layout editor")
            if missing:
                reply = QMessageBox.warning(
                    self, "Incomplete Selection",
                    f"No {'/'.join(missing)} selected. Proceed anyway?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply == QMessageBox.No:
                    return
            if config.install_dir and not os.path.isdir(config.install_dir):
                try:
                    Path(config.install_dir).mkdir(parents=True, exist_ok=True)
                except OSError:
                    QMessageBox.warning(self, "Invalid Directory", f"Cannot create directory: {config.install_dir}")
                    return
            self.stacked.setCurrentIndex(1)
            self._update_nav()
            self.check_page.run_check()

    def _go_to_choices(self):
        self.stacked.setCurrentIndex(0)
        self._update_nav()

    def _on_next_action(self):
        idx = self.stacked.currentIndex()
        if idx == 0:
            self._on_next()
        elif idx == 1:
            self.check_page._on_install()

    def _on_install_ready(self, enabled: bool):
        if self.stacked.currentIndex() == 1:
            self.next_btn.setEnabled(enabled)

    def _on_back_allowed(self, enabled: bool):
        if self.stacked.currentIndex() == 1:
            self.back_btn.setEnabled(enabled)

    def closeEvent(self, event: QCloseEvent):
        if self.check_page.executor and self.check_page.executor.isRunning():
            self.check_page.executor.cancel()
            self.check_page.executor.wait(3000)
        if hasattr(self.check_page, "worker") and self.check_page.worker and self.check_page.worker.isRunning():
            self.check_page.worker.quit()
            self.check_page.worker.wait(2000)
        QApplication.instance().quit()
        event.accept()
