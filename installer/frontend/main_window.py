import os
import signal
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QMessageBox,
    QApplication,
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
        self.current_step = 0

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

        default_base = ""
        if env_pdk_root and env_pdk:
            default_base = env_pdk_root
        elif self.config.pdk_root:
            default_base = self.config.pdk_root
        if default_base:
            self.choice_page.set_base_dir(default_base)

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
        self.step_label = QLabel("Step 1 of 3: Configuration")
        self.step_label.setObjectName("step_label")
        self.step_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        nav_lay.addWidget(self.step_label)
        nav_lay.addStretch()

        self.back_btn = QPushButton("< Back")
        self.back_btn.setFixedWidth(100)
        self.back_btn.setObjectName("back_btn")
        self.back_btn.clicked.connect(self._on_back)
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

        self.check_page.nav_state_changed.connect(self._on_nav_state_changed)
        self.choice_page.skip_tool_check_changed.connect(self._on_skip_tool_check_toggled)
        self._update_ui_for_step()

    def _step_name(self, idx: int) -> str:
        names = [
            "Configuration",
            "Tool Requirements Check",
            "Install",
        ]
        return names[idx]

    def _update_ui_for_step(self):
        self.step_label.setText(f"Step {self.current_step + 1} of 3: {self._step_name(self.current_step)}")
        self.header_label.setText(self._step_name(self.current_step))

        self.back_btn.show()
        self.next_btn.show()
        self.close_btn.show()

        if self.current_step == 0:
            self.back_btn.hide()
            skip = self.choice_page.skip_tool_check_cb.isChecked()
            if skip:
                self.next_btn.setText("Install")
                self.next_btn.setObjectName("install_btn")
            else:
                self.next_btn.setText("Next >")
                self.next_btn.setObjectName("")
            self.next_btn.setEnabled(True)
            self.next_btn.setStyle(self.next_btn.style())
        elif self.current_step == 1:
            self.back_btn.show()
            self.back_btn.setEnabled(True)
            self.next_btn.setText("Next >")
            self.next_btn.setObjectName("")
            self.next_btn.setEnabled(False)
            self.next_btn.setStyle(self.next_btn.style())
        else:
            self.back_btn.show()
            self.back_btn.setEnabled(False)
            self.next_btn.hide()

    def _go_to_step(self, step: int):
        self.current_step = step
        if step == 0:
            self.stacked.setCurrentIndex(0)
        else:
            self.stacked.setCurrentIndex(1)
        self._update_ui_for_step()

        if step == 1:
            self.check_page.show_tool_selection()
        elif step == 2:
            self.check_page.start_env_and_install()

    def _on_next_action(self):
        if self.current_step == 0:
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
                    self,
                    "Incomplete Selection",
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
                    QMessageBox.warning(
                        self,
                        "Invalid Directory",
                        f"Cannot create directory: {config.install_dir}",
                    )
                    return
            if config.skip_tool_check:
                self._go_to_step(2)
            else:
                self._go_to_step(1)
        elif self.current_step == 1:
            if self.check_page._tc_phase == "selection":
                self.check_page.run_tool_check()
            else:
                self._go_to_step(2)
        elif self.current_step == 2:
            self.check_page.start_install()

    def _on_back(self):
        if self.current_step == 1:
            self._go_to_step(0)
        elif self.current_step == 2:
            self._go_to_step(1)

    def _on_skip_tool_check_toggled(self, skip: bool):
        if self.current_step == 0:
            if skip:
                self.next_btn.setText("Install")
                self.next_btn.setObjectName("install_btn")
            else:
                self.next_btn.setText("Next >")
                self.next_btn.setObjectName("")
            self.next_btn.setStyle(self.next_btn.style())

    def _on_nav_state_changed(self, state: dict):
        if self.current_step not in (1, 2):
            return
        if "next_enabled" in state:
            self.next_btn.setEnabled(bool(state["next_enabled"]))
            if self.current_step == 2 and state.get("next_enabled"):
                self.next_btn.show()
        if "next_text" in state:
            text = state["next_text"]
            if text:
                self.next_btn.setText(text)
                if text == "Install":
                    self.next_btn.setObjectName("install_btn")
                else:
                    self.next_btn.setObjectName("")
                self.next_btn.setStyle(self.next_btn.style())
        if "back_enabled" in state:
            self.back_btn.setEnabled(bool(state["back_enabled"]))

    def closeEvent(self, event: QCloseEvent):
        cp = self.check_page
        if cp.executor and cp.executor.isRunning():
            cp.executor.cancel()
            cp.executor.wait(1200)
        if cp.tool_worker and cp.tool_worker.isRunning():
            cp.tool_worker.quit()
            cp.tool_worker.wait(1000)
            cp.tool_worker.terminate()
        if cp.install_worker and cp.install_worker.isRunning():
            cp.install_worker.quit()
            cp.install_worker.wait(1000)
            cp.install_worker.terminate()
        app = QApplication.instance()
        if app:
            app.quit()
        self._kill_descendant_processes()
        event.accept()
        os._exit(0)

    def _kill_descendant_processes(self):
        parent_pid = os.getpid()

        def child_pids(ppid: int):
            children = []
            for entry in os.listdir("/proc"):
                if not entry.isdigit():
                    continue
                stat_path = os.path.join("/proc", entry, "stat")
                try:
                    with open(stat_path, "r", encoding="utf-8") as f:
                        fields = f.read().split()
                    if len(fields) > 3 and int(fields[3]) == ppid:
                        children.append(int(entry))
                except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
                    continue
            return children

        to_visit = [parent_pid]
        descendants = set()
        while to_visit:
            current = to_visit.pop()
            for cpid in child_pids(current):
                if cpid not in descendants:
                    descendants.add(cpid)
                    to_visit.append(cpid)

        for pid in descendants:
            try:
                os.kill(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass

        time.sleep(0.15)

        for pid in descendants:
            try:
                os.kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
