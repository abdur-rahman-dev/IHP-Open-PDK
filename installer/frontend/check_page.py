import os
import re
import subprocess
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QProgressBar,
    QGroupBox,
    QMessageBox,
    QFileDialog,
    QTextEdit,
    QCheckBox,
    QScrollArea,
    QGridLayout,
    QFrame,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor, QIcon
from PySide6.QtWidgets import QStyle

from installer.backend.models import (
    InstallPlan,
    ToolStatusEnum,
    ToolInfo,
    InstallConfig,
    ExecStepStatus,
)
from installer.backend.checker import (
    check_tools_for_names,
    check_environment,
    build_install_plan,
    VERSION_FLAGS,
)
from installer.backend.executor import InstallExecutor
from installer.backend.tool_registry import get_tool_check_tool_ids


def _canonical_tool_name(name: str) -> str:
    tool = (name or "").strip()
    if tool in ("openvaf", "openvaf-r", "openvaf/openvaf-r"):
        return "openvaf"
    return tool


def _tool_display_name(name: str) -> str:
    if _canonical_tool_name(name) == "openvaf":
        return "openvaf"
    return name


class ToolCheckWorker(QThread):
    status = Signal(str)
    progress = Signal(int, int)
    done = Signal(list)

    def __init__(self, config: InstallConfig, extra_tools: list[str]):
        super().__init__()
        self.config = config
        self.extra_tools = extra_tools

    def run(self):
        tools = check_tools_for_names(self.extra_tools, self.config)

        total = len(tools)
        if total == 0:
            self.status.emit("No tools to check.")
            self.progress.emit(0, 0)
            self.done.emit([])
            return

        for i, t in enumerate(tools, start=1):
            self.status.emit(f"Checking {_tool_display_name(t.name)} ... {t.status.value}")
            self.progress.emit(i, total)
        self.status.emit("Tool requirement check complete.")
        self.done.emit(tools)


class InstallWorker(QThread):
    status = Signal(str)
    progress = Signal(int, int)
    finished_ok = Signal(bool, str)

    def __init__(self, plan: InstallPlan):
        super().__init__()
        self.executor = InstallExecutor(plan)

    def run(self):
        self.executor.run()
        total = len(self.executor.steps)
        done = sum(
            1
            for s in self.executor.steps
            if s.status in (ExecStepStatus.DONE, ExecStepStatus.FAILED)
        )
        success = all(s.status != ExecStepStatus.FAILED for s in self.executor.steps)
        msg = "Installation completed successfully!" if success else "Installation completed with errors."
        self.progress.emit(done, total)
        self.finished_ok.emit(success, msg)


class CheckPage(QWidget):
    nav_state_changed = Signal(dict)

    ALL_TC_TOOLS = get_tool_check_tool_ids()
    DEFAULT_TC_TOOLS = ["openvaf/openvaf-r", "klayout"]

    def __init__(self, config: InstallConfig, theme_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme_manager = theme_manager
        self.plan: InstallPlan | None = None
        self.tool_worker: ToolCheckWorker | None = None
        self.install_worker: InstallWorker | None = None
        self.executor: InstallExecutor | None = None
        self._tc_phase = "selection"
        self._recommended_versions = self._load_recommended_versions()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.tc_section = QWidget()
        tc_outer = QVBoxLayout()
        tc_outer.setContentsMargins(0, 0, 0, 0)
        tc_outer.setSpacing(6)

        tc_tools_inner = QWidget()
        tc_tools_grid = QGridLayout()
        tc_tools_grid.setContentsMargins(20, 4, 4, 4)
        tc_tools_grid.setSpacing(4)
        self.tc_checks = {}
        for i, tool in enumerate(self.ALL_TC_TOOLS):
            cb = QCheckBox(tool)
            cb.setChecked(False)
            cb.toggled.connect(self._on_tc_check_toggled)
            self.tc_checks[tool] = cb
            r, c = divmod(i, 3)
            tc_tools_grid.addWidget(cb, r, c)
        tc_tools_inner.setLayout(tc_tools_grid)

        self.tc_scroll = QScrollArea()
        self.tc_scroll.setWidget(tc_tools_inner)
        self.tc_scroll.setWidgetResizable(True)
        self.tc_scroll.setMaximumHeight(150)
        tc_outer.addWidget(self.tc_scroll)
        self.tc_section.setLayout(tc_outer)
        root.addWidget(self.tc_section)

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.hide()
        root.addWidget(self.result_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("Preparing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status_label)

        self.tools_group = QGroupBox("Tool Requirements")
        tools_lay = QVBoxLayout()
        self.tools_table = QTableWidget()
        self.tools_table.verticalHeader().setVisible(False)
        self.tools_table.setColumnCount(5)
        self.tools_table.setHorizontalHeaderLabels(
            ["Tool", "Status", "Installed Version", "PDK Tested", "Path"]
        )
        header = self.tools_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self.tools_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tools_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tools_table.hide()
        tools_lay.addWidget(self.tools_table)

        refresh_row = QHBoxLayout()
        refresh_row.addStretch()
        self.refresh_all_btn = QPushButton()
        self.refresh_all_btn.setObjectName("icon_btn")
        self.refresh_all_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self.refresh_all_btn.setToolTip("Re-check all custom paths")
        self.refresh_all_btn.setFixedSize(32, 32)
        self.refresh_all_btn.clicked.connect(self._on_refresh_all)
        refresh_row.addWidget(self.refresh_all_btn)
        tools_lay.addLayout(refresh_row)

        self.tools_group.setLayout(tools_lay)
        self.tools_group.hide()
        root.addWidget(self.tools_group)

        self.env_group = QGroupBox("Environment Variables")
        env_lay = QVBoxLayout()
        self.env_scroll = QScrollArea()
        self.env_scroll.setWidgetResizable(True)
        self.env_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.env_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.env_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.env_report_widget = QWidget()
        self.env_report_layout = QVBoxLayout(self.env_report_widget)
        self.env_report_layout.setContentsMargins(0, 0, 0, 0)
        self.env_report_layout.setSpacing(10)
        self.env_report_layout.addStretch()
        self.env_scroll.setWidget(self.env_report_widget)
        self.env_scroll.hide()
        env_lay.addWidget(self.env_scroll)
        self.env_group.setLayout(env_lay)
        self.env_group.hide()
        root.addWidget(self.env_group)

        self.install_result_label = QLabel("")
        self.install_result_label.setAlignment(Qt.AlignCenter)
        self.install_result_label.hide()
        root.addWidget(self.install_result_label)

        self.install_log = QTextEdit()
        self.install_log.setReadOnly(True)
        self.install_log.hide()
        root.addWidget(self.install_log)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("dim_note")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.hide()
        root.addWidget(self.hint_label)

    def reset_view(self):
        self.tc_section.hide()
        self.result_label.hide()
        self.progress_bar.hide()
        self.progress_bar.setValue(0)
        self.status_label.setText("Preparing...")
        self.status_label.show()
        self.tools_group.hide()
        self.tools_table.hide()
        self.env_group.hide()
        self.env_scroll.hide()
        self.install_log.hide()
        self.install_log.clear()
        self.install_result_label.hide()
        self.hint_label.hide()

    def _clear_env_report(self):
        while self.env_report_layout.count() > 1:
            item = self.env_report_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

    def _make_env_block(self, title: str, current_value: str, action: str) -> QWidget:
        block = QWidget()
        lay = QVBoxLayout(block)
        lay.setContentsMargins(8, 6, 8, 6)
        lay.setSpacing(4)

        title_label = QLabel(title)
        title_label.setObjectName("env_item_title")
        current_label = QLabel(f"Current value: {current_value}")
        current_label.setObjectName("subtitle")
        current_label.setWordWrap(True)
        current_label.setToolTip(current_value if current_value != "---" else "")
        action_label = QLabel(f"Action: {action}")
        action_label.setObjectName("dim_note")
        action_label.setWordWrap(True)

        lay.addWidget(title_label)
        lay.addWidget(current_label)
        lay.addWidget(action_label)

        divider = QLabel("")
        divider.setFixedHeight(1)
        divider.setObjectName("subseparator")
        lay.addWidget(divider)
        return block

    def _load_recommended_versions(self) -> dict:
        versions = {}
        vpath = Path(__file__).resolve().parent.parent.parent / "versions.txt"
        if not vpath.exists():
            return versions
        name_map = {"Python": "python3"}
        with open(vpath, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(None, 1)
                if len(parts) == 2:
                    key = name_map.get(parts[0], parts[0])
                    versions[key] = parts[1]
        return versions

    def _any_tc_selected(self) -> bool:
        return any(cb.isChecked() for cb in self.tc_checks.values())

    def _on_tc_check_toggled(self):
        if self._tc_phase != "selection":
            return
        self.nav_state_changed.emit({
            "next_enabled": self._any_tc_selected(),
            "next_text": "Check",
        })

    def show_tool_selection(self):
        self.reset_view()
        self._tc_phase = "selection"
        self.tc_section.show()
        self.tc_scroll.show()
        for tool, cb in self.tc_checks.items():
            cb.setChecked(tool in self.DEFAULT_TC_TOOLS)
        self.status_label.hide()
        self.hint_label.setText("Select tools to check, then click Check.")
        self.hint_label.show()

        self.nav_state_changed.emit({
            "next_enabled": self._any_tc_selected(),
            "next_text": "Check",
        })

    def run_tool_check(self):
        self._tc_phase = "checking"
        self.tc_section.hide()
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.status_label.setText("Starting tool requirement checks...")
        self.status_label.show()
        self.hint_label.setText("Checking selected requirements...")
        self.hint_label.show()

        self.config.tools_to_check = [
            t for t, cb in self.tc_checks.items() if cb.isChecked()
        ]
        self.tool_worker = ToolCheckWorker(self.config, list(self.config.tools_to_check))
        self.tool_worker.status.connect(self.status_label.setText)
        self.tool_worker.progress.connect(self._on_tool_progress)
        self.tool_worker.done.connect(self._on_tool_done)
        self.tool_worker.start()

        self.nav_state_changed.emit({
            "next_enabled": False,
            "next_text": "Check",
        })

    def _on_tool_progress(self, done: int, total: int):
        return

    def _on_tool_done(self, tools):
        self._tc_phase = "report"
        if self.plan is None:
            self.plan = build_install_plan(self.config)
        self.plan.tools = tools

        self.progress_bar.hide()
        self.status_label.hide()
        self._populate_tools(tools)

        has_missing = any(not t.installed for t in tools)
        has_error = any(t.status == ToolStatusEnum.ERROR for t in tools)
        if has_error:
            self.result_label.setText("ERRORS found - see details below")
            self.result_label.setObjectName("result_error")
        elif has_missing:
            self.result_label.setText("Some tools not found - provide custom paths or install them")
            self.result_label.setObjectName("result_warn")
        else:
            self.result_label.setText("All checked tools found")
            self.result_label.setObjectName("result_ok")
        self.result_label.setStyle(self.result_label.style())
        self.result_label.show()

        self._check_compiler_requirement(tools)

    def _check_compiler_requirement(self, tools):
        has_sim = len(self.config.get_effective_simulators()) > 0 and self.config.compile_verilog_a
        has_compiler = any(
            _canonical_tool_name(t.name) == "openvaf" and t.installed
            for t in tools
        )
        can_next = True
        if has_sim and not has_compiler:
            self.result_label.setText(
                "ERROR: Simulator selected but openvaf/openvaf-r compiler not found."
            )
            self.result_label.setObjectName("result_error")
            self.result_label.setStyle(self.result_label.style())
            can_next = False

        self.hint_label.setText("Click Next to continue to install.")
        self.hint_label.show()
        self.nav_state_changed.emit({
            "next_enabled": can_next,
            "next_text": "Next >",
        })

    def start_env_and_install(self):
        if not self.plan:
            self.plan = build_install_plan(self.config)

        self.reset_view()
        self.status_label.setText("Checking environment variables...")
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)

        env_checks = check_environment(self.config)
        self.plan.env_checks = env_checks
        self._populate_env(env_checks)

        self.progress_bar.hide()
        self.status_label.hide()
        self.result_label.setText("Environment check results")
        self.result_label.setObjectName("result_ok")
        self.result_label.setStyle(self.result_label.style())
        self.result_label.show()

        if not self.config.compile_verilog_a:
            pdk_root = self.config.get_target_pdk_root()
            pdk = self.config.pdk.value
            osdi_dir = os.path.join(pdk_root, pdk, "libs.tech", "ngspice", "osdi")
            if not os.path.isdir(osdi_dir) or not os.listdir(osdi_dir):
                self.result_label.setText(
                    "Warning: Verilog-A compilation skipped but OSDI models not found.\n"
                    "Some simulations may not work."
                )
                self.result_label.setObjectName("result_warn")
                self.result_label.setStyle(self.result_label.style())

        self.hint_label.setText("Click Install to proceed.")
        self.hint_label.show()

        can_install = not self.plan.has_errors()
        self.nav_state_changed.emit({
            "next_enabled": can_install,
            "next_text": "Install",
            "back_enabled": True,
        })

    def start_install(self):
        if not self.plan:
            self.plan = build_install_plan(self.config)

        self.env_group.hide()
        self.install_result_label.hide()
        self.hint_label.hide()
        self.result_label.hide()
        self.progress_bar.show()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(False)
        self.status_label.setText("Installing... please wait.")
        self.status_label.show()
        self.install_log.show()

        self.executor = InstallExecutor(self.plan)
        self.executor.step_started.connect(self._on_install_step_started)
        self.executor.step_finished.connect(self._on_install_step_finished)
        self.executor.log_line.connect(self._on_install_log)
        self.executor.all_done.connect(self._on_install_done)
        self.executor.start()

        self.nav_state_changed.emit({
            "next_enabled": False,
            "next_text": "Install",
            "back_enabled": False,
        })

    def _on_install_step_started(self, idx: int, label: str):
        self.status_label.setText(f"Step {idx + 1}: {label}")

    def _on_install_step_finished(self, idx: int, label: str, ok: bool):
        return

    def _on_install_log(self, line: str):
        self.install_log.append(line)

    def _on_install_done(self, success: bool):
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(100)
        self.progress_bar.hide()
        self.status_label.hide()
        if self.executor:
            try:
                self.executor.log_line.disconnect(self._on_install_log)
            except (TypeError, RuntimeError):
                pass
        if success:
            self.install_result_label.setText("Installation completed successfully!")
            self.install_result_label.setObjectName("result_ok")
        else:
            self.install_result_label.setText("Installation failed. Review the log below.")
            self.install_result_label.setObjectName("result_error")
        self.install_result_label.setStyle(self.install_result_label.style())
        self.install_result_label.show()

        self.nav_state_changed.emit({
            "next_enabled": False,
            "next_text": "",
            "back_enabled": False,
        })

    def _get_status_color(self, status: ToolStatusEnum) -> QColor:
        if status == ToolStatusEnum.OK:
            return self.theme_manager.get_color("status_ok")
        if status == ToolStatusEnum.WARNING:
            return self.theme_manager.get_color("status_warn")
        if status == ToolStatusEnum.ERROR:
            return self.theme_manager.get_color("status_error")
        return self.theme_manager.get_color("text_secondary")

    def _check_custom_path_version(self, file_path: str, tool_name: str) -> str | None:
        canonical = _canonical_tool_name(tool_name)
        if canonical not in VERSION_FLAGS:
            return None
        flags_list = VERSION_FLAGS.get(canonical, ["--version"])
        for flag in flags_list:
            try:
                result = subprocess.run(
                    [file_path] + flag.split(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    check=False,
                    timeout=10,
                    start_new_session=True,
                )
                output = (result.stdout + result.stderr).strip()
                if not output:
                    continue
                match = re.search(r"(v?\d+\.\d+[\.\d]*[\w\-]*)", output)
                if match:
                    return match.group(1)
            except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
                pass
        return None

    def _refresh_overall_status(self):
        tools = self.plan.tools if self.plan else []
        has_missing = any(not t.installed for t in tools)
        has_error = any(t.status == ToolStatusEnum.ERROR for t in tools)
        if has_error:
            self.result_label.setText("ERRORS found - see details below")
            self.result_label.setObjectName("result_error")
        elif has_missing:
            self.result_label.setText("Some tools not found - provide custom paths or install them")
            self.result_label.setObjectName("result_warn")
        else:
            self.result_label.setText("All checked tools found")
            self.result_label.setObjectName("result_ok")
        self.result_label.setStyle(self.result_label.style())
        self._check_compiler_requirement(tools)

    def _check_klayout_python_from_path(self, selected_dir: str) -> tuple:
        init_path = os.path.join(selected_dir, "__init__.py")
        if not os.path.isfile(init_path):
            parent = os.path.dirname(selected_dir.rstrip("/"))
            init_path = os.path.join(parent, "__init__.py")
            if not os.path.isfile(init_path):
                return None, False

        pkg_dir = os.path.dirname(init_path)
        site_dir = os.path.dirname(pkg_dir)
        ver = None

        try:
            import glob
            meta_files = glob.glob(
                os.path.join(site_dir, "klayout*.dist-info", "METADATA")
            )
            if meta_files:
                with open(meta_files[0], "r") as f:
                    for line in f:
                        if line.lower().startswith("version:"):
                            ver = line.split(":", 1)[1].strip()
                            break
        except Exception:
            pass

        if not ver:
            try:
                with open(init_path, "r") as f:
                    content = f.read()
                m = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
                if m:
                    ver = m.group(1)
            except Exception:
                pass

        return ver, True

    def _check_klayout_python_mismatch(self, py_ver):
        from installer.backend.checker import parse_version
        for r in range(self.tools_table.rowCount()):
            item = self.tools_table.item(r, 0)
            if not item:
                continue
            tool_obj = item.data(Qt.UserRole)
            if tool_obj and tool_obj.name == "klayout":
                bin_ver = self.tools_table.item(r, 2).text()
                if bin_ver and bin_ver != "N/A" and py_ver:
                    if parse_version(py_ver) != parse_version(bin_ver):
                        return True, f"Version mismatch: binary {bin_ver} vs package {py_ver}"
                break
        return False, ""

    def _dialog_start_dir(self, current_text: str, expect_file: bool = False) -> str:
        path = (current_text or "").strip()
        if not path:
            return ""
        if expect_file and os.path.isfile(path):
            return os.path.dirname(path)
        if os.path.isdir(path):
            return path
        parent = os.path.dirname(path)
        if parent and os.path.isdir(parent):
            return parent
        return ""

    def _populate_tools(self, tools):
        self.tools_table.setRowCount(len(tools))
        self.tools_group.show()
        self.tools_table.show()
        self.tools_table.verticalHeader().setDefaultSectionSize(44)
        for i, t in enumerate(tools):
            name_item = QTableWidgetItem(_tool_display_name(t.name))
            name_item.setData(Qt.UserRole, t)
            self.tools_table.setItem(i, 0, name_item)

            status_item = QTableWidgetItem(t.status.value)
            status_item.setForeground(self._get_status_color(t.status))
            self.tools_table.setItem(i, 1, status_item)

            self.tools_table.setItem(i, 2, QTableWidgetItem(t.version or "N/A"))

            canonical = _canonical_tool_name(t.name)
            rec = self._recommended_versions.get(canonical, "N/A")
            self.tools_table.setItem(i, 3, QTableWidgetItem(rec))

            if t.name == "klayout-python":
                path_widget = QWidget()
                path_lay = QHBoxLayout()
                path_lay.setContentsMargins(2, 2, 2, 2)
                path_edit = QLineEdit()
                path_edit.setFixedHeight(32)
                path_edit.setPlaceholderText("Select klayout package dir...")
                if t.install_path:
                    display = os.path.dirname(t.install_path) if t.install_path.endswith("__init__.py") else t.install_path
                    path_edit.setText(display)
                path_edit.setToolTip(path_edit.text())
                browse_btn = QPushButton()
                browse_btn.setObjectName("icon_btn")
                browse_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                browse_btn.setFixedSize(32, 32)
                row = i

                def make_klayout_py_browse_cb(r, le):
                    def cb():
                        start_dir = self._dialog_start_dir(le.text())
                        d = QFileDialog.getExistingDirectory(
                            self, "Select klayout Python package directory", start_dir
                        )
                        if not d:
                            return
                        le.setText(d)
                        le.setToolTip(d)

                        ver, valid = self._check_klayout_python_from_path(d)
                        if valid:
                            mismatch, mismatch_msg = self._check_klayout_python_mismatch(ver)
                            if mismatch:
                                self.tools_table.item(r, 1).setText("WARN")
                                self.tools_table.item(r, 1).setForeground(
                                    self.theme_manager.get_color("status_warn")
                                )
                            else:
                                self.tools_table.item(r, 1).setText("OK")
                                self.tools_table.item(r, 1).setForeground(
                                    self.theme_manager.get_color("status_ok")
                                )
                            self.tools_table.item(r, 2).setText(ver or "found")
                            tool_item = self.tools_table.item(r, 0)
                            tool_obj = tool_item.data(Qt.UserRole) if tool_item else None
                            if tool_obj:
                                tool_obj.installed = True
                                tool_obj.version = ver
                                tool_obj.status = ToolStatusEnum.WARNING if mismatch else ToolStatusEnum.OK
                                tool_obj.message = mismatch_msg
                                tool_obj.install_path = os.path.join(d, "__init__.py")
                        else:
                            self.tools_table.item(r, 1).setText("MISSING")
                            self.tools_table.item(r, 1).setForeground(
                                self.theme_manager.get_color("status_error")
                            )
                        self._refresh_overall_status()

                    return cb

                browse_btn.clicked.connect(make_klayout_py_browse_cb(row, path_edit))
                path_lay.addWidget(path_edit)
                path_lay.addWidget(browse_btn)
                path_widget.setLayout(path_lay)
                self.tools_table.setCellWidget(i, 4, path_widget)
            elif t.installed:
                display_path = t.install_path or ""
                path_item = QTableWidgetItem(display_path)
                path_item.setToolTip(display_path)
                self.tools_table.setItem(i, 4, path_item)
            else:
                path_widget = QWidget()
                path_lay = QHBoxLayout()
                path_lay.setContentsMargins(2, 2, 2, 2)
                path_edit = QLineEdit()
                path_edit.setFixedHeight(32)
                path_edit.setPlaceholderText("Select executable...")
                browse_btn = QPushButton()
                browse_btn.setObjectName("icon_btn")
                browse_btn.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon))
                browse_btn.setFixedSize(32, 32)
                row = i

                def make_browse_cb(r, le):
                    def cb():
                        tool_item = self.tools_table.item(r, 0)
                        tool_obj = tool_item.data(Qt.UserRole) if tool_item else None
                        tool_name = tool_obj.name if tool_obj else ""
                        start_dir = self._dialog_start_dir(le.text(), expect_file=True)
                        file_path, _ = QFileDialog.getOpenFileName(
                            self, f"Select {tool_name} executable", start_dir
                        )
                        if not file_path:
                            return
                        le.setText(file_path)
                        le.setToolTip(file_path)

                        ver = self._check_custom_path_version(file_path, tool_name)
                        if ver:
                            self.tools_table.item(r, 1).setText("OK")
                            self.tools_table.item(r, 1).setForeground(
                                self.theme_manager.get_color("status_ok")
                            )
                            self.tools_table.item(r, 2).setText(ver)
                            if tool_obj:
                                tool_obj.installed = True
                                tool_obj.version = ver
                                tool_obj.status = ToolStatusEnum.OK
                        else:
                            try:
                                is_exec = os.path.isfile(file_path) and os.access(file_path, os.X_OK)
                            except OSError:
                                is_exec = False
                            if is_exec:
                                self.tools_table.item(r, 1).setText("OK")
                                self.tools_table.item(r, 1).setForeground(
                                    self.theme_manager.get_color("status_ok")
                                )
                                if tool_obj:
                                    tool_obj.installed = True
                                    tool_obj.status = ToolStatusEnum.OK
                            else:
                                return

                        self._refresh_overall_status()

                    return cb

                browse_btn.clicked.connect(make_browse_cb(row, path_edit))
                path_lay.addWidget(path_edit)
                path_lay.addWidget(browse_btn)
                path_widget.setLayout(path_lay)
                self.tools_table.setCellWidget(i, 4, path_widget)

    def _on_refresh_all(self):
        for r in range(self.tools_table.rowCount()):
            cell = self.tools_table.cellWidget(r, 4)
            if not cell:
                continue
            le = None
            for child in cell.findChildren(QLineEdit):
                le = child
                break
            if not le:
                continue
            custom_path = le.text().strip()
            if not custom_path:
                continue
            le.setToolTip(custom_path)

            tool_item = self.tools_table.item(r, 0)
            tool_obj = tool_item.data(Qt.UserRole) if tool_item else None
            tool_name = tool_obj.name if tool_obj else ""

            if tool_name == "klayout-python":
                ver, valid = self._check_klayout_python_from_path(custom_path)
                if valid:
                    mismatch, mismatch_msg = self._check_klayout_python_mismatch(ver)
                    if mismatch:
                        self.tools_table.item(r, 1).setText("WARN")
                        self.tools_table.item(r, 1).setForeground(
                            self.theme_manager.get_color("status_warn")
                        )
                    else:
                        self.tools_table.item(r, 1).setText("OK")
                        self.tools_table.item(r, 1).setForeground(
                            self.theme_manager.get_color("status_ok")
                        )
                    self.tools_table.item(r, 2).setText(ver or "found")
                    if tool_obj:
                        tool_obj.installed = True
                        tool_obj.version = ver
                        tool_obj.status = ToolStatusEnum.WARNING if mismatch else ToolStatusEnum.OK
                        tool_obj.message = mismatch_msg
                        tool_obj.install_path = os.path.join(custom_path, "__init__.py")
                else:
                    self.tools_table.item(r, 1).setText("MISSING")
                    self.tools_table.item(r, 1).setForeground(
                        self.theme_manager.get_color("status_error")
                    )
                    if tool_obj:
                        tool_obj.installed = False
                        tool_obj.status = ToolStatusEnum.ERROR
            else:
                ver = self._check_custom_path_version(custom_path, tool_name)
                if ver:
                    self.tools_table.item(r, 1).setText("OK")
                    self.tools_table.item(r, 1).setForeground(
                        self.theme_manager.get_color("status_ok")
                    )
                    self.tools_table.item(r, 2).setText(ver)
                    if tool_obj:
                        tool_obj.installed = True
                        tool_obj.version = ver
                        tool_obj.status = ToolStatusEnum.OK
                else:
                    try:
                        is_exec = os.path.isfile(custom_path) and os.access(custom_path, os.X_OK)
                    except OSError:
                        is_exec = False
                    if is_exec:
                        self.tools_table.item(r, 1).setText("OK")
                        self.tools_table.item(r, 1).setForeground(
                            self.theme_manager.get_color("status_ok")
                        )
                        if tool_obj:
                            tool_obj.installed = True
                            tool_obj.status = ToolStatusEnum.OK
                    else:
                        self.tools_table.item(r, 1).setText("MISSING")
                        self.tools_table.item(r, 1).setForeground(
                            self.theme_manager.get_color("status_error")
                        )
                        if tool_obj:
                            tool_obj.installed = False
                            tool_obj.status = ToolStatusEnum.ERROR

        self._refresh_overall_status()

    def _populate_env(self, env_checks):
        if not env_checks:
            return
        self._clear_env_report()
        self.env_group.show()
        self.env_scroll.show()

        for e in env_checks:
            current_value = e.current_value or "---"
            action = e.action if e.is_set else f"{e.action} \u2192 {e.expected_value or ''}"
            self.env_report_layout.insertWidget(
                self.env_report_layout.count() - 1,
                self._make_env_block(e.variable, current_value, action),
            )
