import os
import signal
import time
from copy import deepcopy
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
    QScrollArea,
)
from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QFont, QCloseEvent, QPixmap

from installer.backend.models import InstallConfig, GitHubSourceMode, PDKSourceType
from installer.backend.checker import (
    validate_github_commit_input,
    validate_github_source,
    validate_local_source,
)
from installer.frontend.choice_page import ChoicePage
from installer.frontend.check_page import CheckPage
from installer.frontend.tool_check_window import ToolCheckWindow


class GitHubValidationWorker(QThread):
    finished_validation = Signal(int, bool, str, object)

    def __init__(self, request_id: int, config: InstallConfig):
        super().__init__()
        self.request_id = request_id
        self.config = config

    def run(self):
        ok, message = validate_github_source(self.config)
        self.finished_validation.emit(
            self.request_id,
            ok,
            message,
            self.config.resolved_github_commit,
        )


class MainWindow(QMainWindow):
    def __init__(self, theme_manager):
        super().__init__()
        self.config = InstallConfig()
        self.theme_manager = theme_manager
        self.current_step = 0
        self._source_valid = True
        self._install_finished = False
        self._install_succeeded = False
        self._github_validation_worker: GitHubValidationWorker | None = None
        self._github_validation_timer = QTimer(self)
        self._github_validation_timer.setSingleShot(True)
        self._github_validation_timer.setInterval(350)
        self._github_validation_timer.timeout.connect(self._start_pending_github_validation)
        self._github_validation_request_id = 0
        self._latest_github_validation_id = 0
        self._pending_github_validation: tuple[int, InstallConfig] | None = None
        self._github_validation_cache: dict[tuple[str, str], tuple[bool, str, str | None]] = {}
        self.tool_check_window: ToolCheckWindow | None = None

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
        self.setMinimumSize(720, 710)
        self.resize(800, 700)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(8)

        header_row = QHBoxLayout()
        logo_label = QLabel()
        logo_pm = QPixmap(str(Path(__file__).resolve().parent.parent / "assets" / "ihp_logo_without_claim_sRGB.png"))
        logo_label.setPixmap(logo_pm.scaled(48, 48, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        logo_label.setFixedSize(48, 48)
        header_row.addWidget(logo_label)

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
        self.choice_scroll = QScrollArea()
        self.choice_scroll.setWidget(self.choice_page)
        self.choice_scroll.setWidgetResizable(True)
        self.choice_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.check_page = CheckPage(self.config, self.theme_manager)

        self.stacked.addWidget(self.choice_scroll)
        self.stacked.addWidget(self.check_page)

        nav_lay = QHBoxLayout()
        self.step_label = QLabel("Step 1 of 2: Configuration")
        self.step_label.setObjectName("step_label")
        self.step_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        nav_lay.addWidget(self.step_label)
        nav_lay.addStretch()

        self.back_btn = QPushButton("< Back")
        self.back_btn.setFixedWidth(100)
        self.back_btn.setObjectName("back_btn")
        self.back_btn.clicked.connect(self._on_back)
        nav_lay.addWidget(self.back_btn)

        self.tool_check_btn = QPushButton("Tool Check")
        self.tool_check_btn.setFixedWidth(120)
        self.tool_check_btn.clicked.connect(self._open_tool_check_window)
        nav_lay.addWidget(self.tool_check_btn)

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
        self.check_page.install_finished.connect(self._on_install_finished)
        self.choice_page.config_changed.connect(self._on_config_changed)
        self._update_ui_for_step()
        self._refresh_source_validity()

    def _step_name(self, idx: int) -> str:
        names = [
            "Configuration",
            "Install",
        ]
        return names[idx]

    def _update_ui_for_step(self):
        self.step_label.setText(f"Step {self.current_step + 1} of 2: {self._step_name(self.current_step)}")
        self.header_label.setText(self._step_name(self.current_step))

        self.back_btn.show()
        self.next_btn.show()
        self.close_btn.show()

        if self.current_step == 0:
            self.back_btn.hide()
            self.tool_check_btn.show()
            self.next_btn.setText("Next >")
            self.next_btn.setObjectName("")
            self.next_btn.setEnabled(self._can_advance_from_configuration())
            self.next_btn.setStyle(self.next_btn.style())
        else:
            self.back_btn.show()
            self.tool_check_btn.hide()
            self.back_btn.setEnabled(self._install_finished)
            self.back_btn.setText("Start" if self._install_finished and self._install_succeeded else "< Back")
            self.next_btn.hide()

    def _go_to_step(self, step: int):
        self.current_step = step
        self.stacked.setCurrentIndex(step)
        self._update_ui_for_step()

        if step == 1:
            self._install_finished = False
            self._install_succeeded = False
            self.check_page.plan = None
            self.check_page.start_env_and_install()

    def _tool_check_window_is_open(self) -> bool:
        return self.tool_check_window is not None and self.tool_check_window.isVisible()

    def _can_advance_from_configuration(self) -> bool:
        return self._source_valid and not self._tool_check_window_is_open()

    def _open_tool_check_window(self):
        if self._tool_check_window_is_open():
            self.tool_check_window.raise_()
            self.tool_check_window.activateWindow()
            return

        config_snapshot = deepcopy(self.choice_page.get_config())
        self.tool_check_window = ToolCheckWindow(config_snapshot, self.theme_manager, self)
        self.tool_check_window.window_closed.connect(self._on_tool_check_window_closed)
        self.tool_check_window.show()
        self.tool_check_window.raise_()
        self.tool_check_window.activateWindow()
        if self.current_step == 0:
            self.next_btn.setEnabled(self._can_advance_from_configuration())

    def _on_tool_check_window_closed(self):
        self.tool_check_window = None
        if self.current_step == 0:
            self.next_btn.setEnabled(self._can_advance_from_configuration())

    def _on_next_action(self):
        if self.current_step == 0:
            config = self.choice_page.get_config()
            if not self._validate_source(config, show_dialog=True):
                self._refresh_source_validity()
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
            self._go_to_step(1)
        elif self.current_step == 1:
            if self.check_page.confirm_install_if_needed():
                self.check_page.start_install()

    def _on_back(self):
        if self.current_step != 1:
            return
        if self._install_succeeded:
            self.choice_page.reset_to_defaults()
        self._clear_completed_install_state()
        self._refresh_source_validity()
        self._go_to_step(0)

    def _clear_completed_install_state(self):
        self._install_finished = False
        self._install_succeeded = False

    def _on_config_changed(self):
        if self.current_step == 0:
            self._refresh_source_validity()

    def _github_validation_cache_key(self, config: InstallConfig) -> tuple[str, str]:
        return (config.pdk.value, (config.github_commit or "").strip().lower())

    def _invalidate_github_validation(self):
        self._github_validation_request_id += 1
        self._latest_github_validation_id = self._github_validation_request_id
        self._pending_github_validation = None
        self._github_validation_timer.stop()

    def _queue_github_commit_validation(self, config: InstallConfig):
        self._github_validation_request_id += 1
        request_id = self._github_validation_request_id
        self._latest_github_validation_id = request_id
        cache_key = self._github_validation_cache_key(config)
        cached = self._github_validation_cache.get(cache_key)
        if cached is not None:
            ok, message, resolved_commit = cached
            self.config.resolved_github_commit = resolved_commit
            self.choice_page.set_source_status(ok, message if not ok else "")
            self._source_valid = ok
            if self.current_step == 0:
                self.next_btn.setEnabled(self._can_advance_from_configuration())
            return

        self._pending_github_validation = (request_id, deepcopy(config))
        self.config.resolved_github_commit = None
        self.choice_page.set_source_pending_status("Validating commit...")
        self._source_valid = False
        if self.current_step == 0:
            self.next_btn.setEnabled(False)
        if self._github_validation_worker and self._github_validation_worker.isRunning():
            return
        self._github_validation_timer.start()

    def _start_pending_github_validation(self):
        if not self._pending_github_validation:
            return
        if self._github_validation_worker and self._github_validation_worker.isRunning():
            return
        request_id, config = self._pending_github_validation
        self._pending_github_validation = None
        self._github_validation_worker = GitHubValidationWorker(request_id, config)
        self._github_validation_worker.finished_validation.connect(self._on_github_validation_finished)
        self._github_validation_worker.start()

    def _on_github_validation_finished(self, request_id: int, ok: bool, message: str, resolved_commit):
        sender = self.sender()
        if sender is self._github_validation_worker:
            self._github_validation_worker = None
        current_config = self.choice_page.get_config()
        cache_key = self._github_validation_cache_key(current_config)
        if request_id == self._latest_github_validation_id:
            self.config.resolved_github_commit = resolved_commit if ok else None
            self._github_validation_cache[cache_key] = (ok, message, resolved_commit if ok else None)
            self.choice_page.set_source_status(ok, message if not ok else "")
            self._source_valid = ok
            if self.current_step == 0:
                self.next_btn.setEnabled(self._can_advance_from_configuration())
        if self._pending_github_validation:
            self._github_validation_timer.start()

    def _validate_source(self, config: InstallConfig, show_dialog: bool = False) -> bool:
        self._invalidate_github_validation()
        if config.pdk_source_type == PDKSourceType.LOCAL:
            ok, message = validate_local_source(config)
            self.choice_page.set_source_status(ok, message)
            if not ok and show_dialog:
                QMessageBox.warning(
                    self,
                    "Invalid Local PDK Source",
                    f"The selected local source does not look like a valid {config.get_selected_pdk_dirname()} PDK.\n\n{message}",
                )
            return ok

        if config.github_source_mode == GitHubSourceMode.COMMIT and (config.github_commit or "").strip():
            ok, message = validate_github_commit_input(config.github_commit or "")
            if not ok:
                config.resolved_github_commit = None
                self.choice_page.set_source_status(False, message)
                if show_dialog:
                    QMessageBox.warning(self, "GitHub Source Unavailable", message)
                return False

        ok, message = validate_github_source(config)
        self.choice_page.set_source_status(ok, message if not ok else "")
        if not ok and show_dialog:
            QMessageBox.warning(
                self,
                "GitHub Source Unavailable",
                message,
            )
        return ok

    def _refresh_source_validity(self):
        config = self.choice_page.get_config()
        if config.pdk_source_type == PDKSourceType.GITHUB:
            commit = (config.github_commit or "").strip()
            if config.github_source_mode == GitHubSourceMode.COMMIT and commit:
                ok, message = validate_github_commit_input(commit)
                if not ok:
                    self._invalidate_github_validation()
                    self.config.resolved_github_commit = None
                    self.choice_page.set_source_status(False, message)
                    self._source_valid = False
                else:
                    self._queue_github_commit_validation(config)
                if self.current_step == 0:
                    self.next_btn.setEnabled(self._can_advance_from_configuration())
                return

        self._source_valid = self._validate_source(config, show_dialog=False)
        if self.current_step == 0:
            self.next_btn.setEnabled(self._can_advance_from_configuration())

    def _on_nav_state_changed(self, state: dict):
        if self.current_step != 1:
            return
        if "next_enabled" in state:
            self.next_btn.setEnabled(bool(state["next_enabled"]))
            if state.get("next_text"):
                self.next_btn.show()
        if "next_text" in state:
            text = state["next_text"]
            if text:
                self.next_btn.setText(text)
                if text == "Install":
                    self.next_btn.setObjectName("install_btn")
                else:
                    self.next_btn.setObjectName("")
                self.next_btn.show()
                self.next_btn.setStyle(self.next_btn.style())
            else:
                self.next_btn.hide()
        if "back_enabled" in state:
            self.back_btn.setEnabled(bool(state["back_enabled"]))

    def _on_install_finished(self, success: bool):
        self._install_finished = True
        self._install_succeeded = success
        self._update_ui_for_step()

    def closeEvent(self, event: QCloseEvent):
        self._invalidate_github_validation()
        if self._github_validation_worker and self._github_validation_worker.isRunning():
            self._github_validation_worker.quit()
            self._github_validation_worker.wait(1000)
            self._github_validation_worker.terminate()
        if self._tool_check_window_is_open():
            self.tool_check_window.close()
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
