import os
import re
import subprocess

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QGroupBox, QTextEdit, QMessageBox, QFileDialog,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from installer.backend.models import (
    InstallPlan, ToolStatusEnum, ToolInfo, EnvCheckResult, InstallConfig,
    ExecStepStatus,
)
from installer.backend.checker import (
    build_install_plan, check_environment, is_program_installed, get_version,
)
from installer.backend.executor import InstallExecutor


class ToolCheckWorker(QThread):
    progress = Signal(str)
    tool_checked = Signal(str, str, str, str)
    done = Signal(object)

    def __init__(self, config: InstallConfig):
        super().__init__()
        self.config = config

    def run(self):
        from installer.backend.checker import check_tools
        self.progress.emit("Checking tools...")
        tools = check_tools(self.config)
        plan = build_install_plan(self.config)
        for t in tools:
            ver = t.version or "---"
            self.tool_checked.emit(t.name, t.status.value, ver, t.message)
        self.progress.emit("Check complete.")
        plan.tools = tools
        self.done.emit(plan)


class CheckPage(QWidget):
    back_requested = Signal()

    def __init__(self, config: InstallConfig, theme_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme_manager = theme_manager
        self.plan: InstallPlan | None = None
        self.executor: InstallExecutor | None = None
        self.worker = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.title = QLabel("Check & Install")
        self.title.setObjectName("page_title")
        self.title.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title)

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.hide()
        root.addWidget(self.result_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Checking...")
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("Preparing...")
        self.status_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status_label)

        self.tools_group = QGroupBox("Tool Check")
        tools_lay = QVBoxLayout()
        self.tools_table = QTableWidget()
        self.tools_table.setColumnCount(5)
        self.tools_table.setHorizontalHeaderLabels(
            ["Tool", "Status", "Version", "Custom Path", "Notes"]
        )
        for col in [0, 3, 4]:
            self.tools_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )
        self.tools_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tools_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tools_table.hide()
        tools_lay.addWidget(self.tools_table)
        self.tools_group.setLayout(tools_lay)
        self.tools_group.hide()
        root.addWidget(self.tools_group)

        self.env_group = QGroupBox("Environment Variables")
        env_lay = QVBoxLayout()
        self.env_table = QTableWidget()
        self.env_table.setColumnCount(4)
        self.env_table.setHorizontalHeaderLabels(
            ["Variable", "Status", "Current Value", "Action"]
        )
        for col in [0, 2, 3]:
            self.env_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )
        self.env_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.env_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.env_table.hide()
        env_lay.addWidget(self.env_table)
        self.env_group.setLayout(env_lay)
        self.env_group.hide()
        root.addWidget(self.env_group)

        self.exec_log = QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setMaximumHeight(120)
        log_font = self.exec_log.font()
        log_font.setFamily("monospace")
        log_font.setPointSize(9)
        self.exec_log.setFont(log_font)
        self.exec_log.hide()
        root.addWidget(self.exec_log)

        self.install_result_label = QLabel("")
        self.install_result_label.setAlignment(Qt.AlignCenter)
        self.install_result_label.hide()
        root.addWidget(self.install_result_label)

        self.hint_label = QLabel("")
        self.hint_label.setObjectName("dim_note")
        self.hint_label.setAlignment(Qt.AlignCenter)
        self.hint_label.hide()
        root.addWidget(self.hint_label)

        btn_lay = QHBoxLayout()
        self.back_btn = QPushButton("< Back")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_lay.addWidget(self.back_btn)
        btn_lay.addStretch()
        self.install_btn = QPushButton("Install")
        self.install_btn.setObjectName("install_btn")
        self.install_btn.clicked.connect(self._on_install)
        self.install_btn.setEnabled(False)
        btn_lay.addWidget(self.install_btn)
        root.addLayout(btn_lay)

    def run_check(self):
        self.progress_bar.show()
        self.tools_group.hide()
        self.env_group.hide()
        self.result_label.hide()
        self.exec_log.hide()
        self.install_result_label.hide()
        self.hint_label.hide()
        self.install_btn.setEnabled(False)
        self.back_btn.setEnabled(True)

        if self.config.check_tools and self.config.tools_to_check:
            self._run_tool_check()
        else:
            self._run_env_check()

    def _run_tool_check(self):
        self.status_label.setText("Checking EDA tools...")
        self.exec_log.show()
        self.exec_log.clear()

        self.worker = ToolCheckWorker(self.config)
        self.worker.progress.connect(self._on_progress)
        self.worker.tool_checked.connect(self._on_tool_checked)
        self.worker.done.connect(self._on_tool_check_done)
        self.worker.start()

    def _on_tool_checked(self, name, status, version, notes):
        line = f"Checking {name} ..... {status}"
        if version and version != "---":
            line += f" ({version})"
        self.exec_log.append(line)

    def _on_tool_check_done(self, plan: InstallPlan):
        self.plan = plan
        self.progress_bar.hide()
        self._populate_tools(plan.tools)

        has_missing = any(not t.installed for t in plan.tools)
        if plan.has_errors():
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

        self._check_compiler_requirement()

        self._run_env_check()

    def _check_compiler_requirement(self):
        if not self.plan:
            return
        from installer.backend.models import Simulator
        has_sim = len(self.config.simulators) > 0
        has_compiler = any(
            t.name in ("openvaf", "openvaf-r") and t.installed
            for t in self.plan.tools
        )
        if has_sim and not has_compiler:
            self.result_label.setText(
                "ERROR: Simulator selected but openvaf/openvaf-r compiler not found.\n"
                "Install it or provide a custom path."
            )
            self.result_label.setObjectName("result_error")
            self.result_label.setStyle(self.result_label.style())
            self.install_btn.setEnabled(False)

    def _run_env_check(self):
        self.status_label.setText("Checking environment variables...")
        env_checks = check_environment(self.config)
        if self.plan:
            self.plan.env_checks = env_checks
        else:
            self.plan = build_install_plan(self.config)
            self.plan.env_checks = env_checks
        self._populate_env(env_checks)

        self.progress_bar.hide()
        can_install = not (self.plan and self.plan.has_errors())
        self.install_btn.setEnabled(can_install)

        self.hint_label.setText("Click Install to proceed.")
        self.hint_label.show()
        self.status_label.setText("Check complete.")

    def _on_progress(self, msg):
        self.status_label.setText(msg)

    def _on_install(self):
        if not self.plan:
            return
        reply = QMessageBox.question(
            self, "Confirm Installation",
            "This will install/configure the PDK.\n\nProceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.install_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.exec_log.show()
        self.exec_log.clear()
        self.install_result_label.hide()
        self.hint_label.hide()

        self.progress_bar.show()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Installing...")
        self.status_label.setText("Installing... please wait.")

        self.executor = InstallExecutor(self.plan)
        self.executor.step_started.connect(self._on_step_started)
        self.executor.step_finished.connect(self._on_step_finished)
        self.executor.all_done.connect(self._on_install_done)
        self.executor.log_line.connect(self._on_log)
        self.executor.start()

    def _on_step_started(self, idx: int, label: str):
        self.exec_log.append(f"[{idx+1}] {label}...")
        self.progress_bar.setFormat(f"Step {idx+1}: {label}")

    def _on_step_finished(self, idx: int, label: str, ok: bool):
        status = "OK" if ok else "FAILED"
        self.exec_log.append(f"    -> {status}")

        if self.executor:
            total = len(self.executor.steps)
            done = sum(
                1 for s in self.executor.steps
                if s.status in (ExecStepStatus.DONE, ExecStepStatus.FAILED)
            )
            pct = int((done / total) * 100) if total > 0 else 100
            self.progress_bar.setValue(pct)

    def _on_log(self, msg: str):
        self.exec_log.append(msg)

    def _on_install_done(self, success: bool):
        self.progress_bar.setValue(100)
        self.back_btn.setEnabled(True)

        if success:
            self.install_result_label.setText("Installation completed successfully!")
            self.install_result_label.setObjectName("result_ok")
            self.status_label.setText("Installation complete.")
            self.progress_bar.setFormat("Done")
        else:
            self.install_result_label.setText("Installation completed with errors. See log above.")
            self.install_result_label.setObjectName("result_error")
            self.status_label.setText("Some steps failed.")
            self.progress_bar.setFormat("Done (with errors)")

        self.install_result_label.setStyle(self.install_result_label.style())
        self.install_result_label.show()

    def _get_status_color(self, status: ToolStatusEnum) -> QColor:
        if status == ToolStatusEnum.OK:
            return self.theme_manager.get_color("status_ok")
        elif status == ToolStatusEnum.WARNING:
            return self.theme_manager.get_color("status_warn")
        elif status == ToolStatusEnum.ERROR:
            return self.theme_manager.get_color("status_error")
        return self.theme_manager.get_color("text_secondary")

    def _populate_tools(self, tools):
        self.tools_table.setRowCount(len(tools))
        self.tools_group.show()
        self.tools_table.show()
        for i, t in enumerate(tools):
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t)
            self.tools_table.setItem(i, 0, name_item)

            status_item = QTableWidgetItem(t.status.value)
            status_item.setForeground(self._get_status_color(t.status))
            self.tools_table.setItem(i, 1, status_item)

            self.tools_table.setItem(i, 2, QTableWidgetItem(t.version or "---"))

            path_widget = QWidget()
            path_lay = QHBoxLayout()
            path_lay.setContentsMargins(2, 2, 2, 2)
            path_label = QLabel("---")
            browse_btn = QPushButton("Browse...")
            browse_btn.setObjectName("browse_btn")
            browse_btn.setFixedWidth(80)
            recheck_btn = QPushButton("Re-check")
            recheck_btn.setFixedWidth(70)
            row = i

            def make_browse_cb(r):
                def cb():
                    d = QFileDialog.getExistingDirectory(
                        self, f"Select directory containing {tools[r].name}"
                    )
                    if d:
                        existing = self.tools_table.item(r, 3)
                        self.tools_table.setItem(r, 3, QTableWidgetItem(d))
                return cb

            def make_recheck_cb(r):
                def cb():
                    path_item = self.tools_table.item(r, 3)
                    custom_dir = path_item.text().strip() if path_item else ""
                    if not custom_dir or custom_dir == "---":
                        return
                    tool_info = self.tools_table.item(r, 0)
                    tool_name = tool_info.text().split("/")[0] if tool_info else ""
                    bin_path = os.path.join(custom_dir, tool_name)
                    if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
                        ver = get_version(tool_name) or "found"
                        self.tools_table.setItem(r, 1, QTableWidgetItem("OK"))
                        ok_color = self.theme_manager.get_color("status_ok")
                        self.tools_table.item(r, 1).setForeground(ok_color)
                        self.tools_table.setItem(r, 2, QTableWidgetItem(ver))
                        self.tools_table.setItem(r, 4, QTableWidgetItem(""))
                    else:
                        try:
                            env = os.environ.copy()
                            env["PATH"] = custom_dir + ":" + env.get("PATH", "")
                            result = subprocess.run(
                                ["which", tool_name],
                                env=env,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL,
                                text=True, timeout=5,
                            )
                            if result.returncode == 0:
                                found = result.stdout.strip()
                                self.tools_table.setItem(r, 1, QTableWidgetItem("OK"))
                                ok_color = self.theme_manager.get_color("status_ok")
                                self.tools_table.item(r, 1).setForeground(ok_color)
                                self.tools_table.setItem(r, 4, QTableWidgetItem(f"Found: {found}"))
                            else:
                                self.tools_table.setItem(r, 1, QTableWidgetItem("MISSING"))
                                err_color = self.theme_manager.get_color("status_error")
                                self.tools_table.item(r, 1).setForeground(err_color)
                                self.tools_table.setItem(r, 4, QTableWidgetItem(f"Not found in {custom_dir}"))
                        except Exception:
                            self.tools_table.setItem(r, 4, QTableWidgetItem("Re-check failed"))
                return cb

            browse_btn.clicked.connect(make_browse_cb(row))
            recheck_btn.clicked.connect(make_recheck_cb(row))

            if not t.installed:
                path_lay.addWidget(browse_btn)
                path_lay.addWidget(recheck_btn)
            else:
                path_label.setText("(system)")
                path_lay.addWidget(path_label)
                browse_btn.hide()
                recheck_btn.hide()

            path_widget.setLayout(path_lay)
            self.tools_table.setCellWidget(i, 3, path_widget)
            self.tools_table.setItem(i, 4, QTableWidgetItem(t.message))

        self.tools_table.resizeColumnsToContents()

    def _populate_env(self, env_checks):
        if not env_checks:
            return
        self.env_table.setRowCount(len(env_checks))
        self.env_group.show()
        self.env_table.show()
        ok_color = self.theme_manager.get_color("status_ok")
        warn_color = self.theme_manager.get_color("status_warn")

        for i, e in enumerate(env_checks):
            self.env_table.setItem(i, 0, QTableWidgetItem(e.variable))
            status = "OK" if e.is_set else "MISSING"
            item = QTableWidgetItem(status)
            item.setForeground(ok_color if e.is_set else warn_color)
            self.env_table.setItem(i, 1, item)
            self.env_table.setItem(i, 2, QTableWidgetItem(e.current_value or "---"))
            self.env_table.setItem(i, 3, QTableWidgetItem(e.action))

        self.env_table.resizeColumnsToContents()
