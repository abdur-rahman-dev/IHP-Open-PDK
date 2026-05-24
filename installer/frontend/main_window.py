import os
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QMessageBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from installer.backend.models import InstallConfig
from installer.frontend.choice_page import ChoicePage
from installer.frontend.check_page import CheckPage
from installer.frontend.plan_page import PlanPage


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

        self._build_ui()

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

        header = QLabel("IHP-Open-PDK Installer")
        header.setFont(QFont("Sans", 16, QFont.Bold))
        header.setObjectName("header_title")
        header.setAlignment(Qt.AlignCenter)
        header_row.addWidget(header, 1)

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
        self.plan_page = PlanPage(self.theme_manager)

        self.stacked.addWidget(self.choice_page)
        self.stacked.addWidget(self.check_page)
        self.stacked.addWidget(self.plan_page)

        nav_lay = QHBoxLayout()
        self.nav_left = QLabel("")
        nav_lay.addWidget(self.nav_left)

        self.step_label = QLabel("Step 1 of 3: Configuration")
        self.step_label.setObjectName("step_label")
        self.step_label.setAlignment(Qt.AlignCenter)
        nav_lay.addWidget(self.step_label)

        self.next_btn = QPushButton("Next >")
        self.next_btn.setFixedWidth(120)
        self.next_btn.clicked.connect(self._on_next)
        nav_lay.addWidget(self.next_btn)

        root.addLayout(nav_lay)

        self.check_page.next_requested.connect(self._go_to_plan)
        self.check_page.back_requested.connect(self._go_to_choices)
        self.plan_page.back_requested.connect(self._go_to_check)

        self._update_nav()

    def _update_nav(self):
        idx = self.stacked.currentIndex()
        total = self.stacked.count()
        self.step_label.setText(f"Step {idx + 1} of {total}: {self._step_name(idx)}")

        if idx == 0:
            self.next_btn.setText("Next >")
            self.next_btn.show()
            self.nav_left.setText("")
        elif idx == 1:
            self.next_btn.hide()
        elif idx == 2:
            self.next_btn.hide()

    def _step_name(self, idx):
        return ["Configuration", "Tool Check", "Installation Plan"][idx]

    def _on_next(self):
        if self.stacked.currentIndex() == 0:
            config = self.choice_page.get_config()
            if not config.simulators:
                QMessageBox.warning(self, "No Simulator", "Please select at least one simulator.")
                return
            if not config.schematic_editors:
                QMessageBox.warning(self, "No Editor", "Please select at least one schematic editor.")
                return
            if not config.layout_editors:
                QMessageBox.warning(self, "No Layout", "Please select at least one layout editor.")
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

    def _go_to_plan(self):
        self.stacked.setCurrentIndex(2)
        self._update_nav()
        if self.check_page.plan:
            self.plan_page.set_plan(self.check_page.plan)

    def _go_to_choices(self):
        self.stacked.setCurrentIndex(0)
        self._update_nav()

    def _go_to_check(self):
        self.stacked.setCurrentIndex(1)
        self._update_nav()
