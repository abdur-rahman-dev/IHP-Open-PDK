import os
import subprocess

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
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
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from installer.backend.models import (
    InstallPlan,
    ToolStatusEnum,
    ToolInfo,
    InstallConfig,
    ExecStepStatus,
    Simulator,
    SchematicEditor,
    LayoutEditor,
)
from installer.backend.checker import (
    check_tools,
    check_environment,
    build_install_plan,
    is_program_installed,
    get_version,
)
from installer.backend.executor import InstallExecutor


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
        tools = check_tools(self.config)

        checked_names = {_canonical_tool_name(t.name) for t in tools}
        for raw in self.extra_tools:
            canonical = _canonical_tool_name(raw)
            if canonical in checked_names:
                continue
            if is_program_installed(raw.split("/")[0]):
                ver = get_version(raw.split("/")[0])
                tools.append(ToolInfo(
                    name=raw, installed=True, version=ver,
                    status=ToolStatusEnum.OK, required=False,
                    category="extra", message="",
                ))
            else:
                tools.append(ToolInfo(
                    name=raw, installed=False,
                    status=ToolStatusEnum.WARNING, required=False,
                    category="extra", message="Not found",
                ))
            checked_names.add(canonical)

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

    ALL_TC_TOOLS = [
        "python3", "pip", "openvaf/openvaf-r",
        "buildxyceplugin", "gnucap-mg-vams", "ngspice",
        "Xyce", "gnucap", "xschem",
        "qucs-s", "klayout", "magic",
        "netgen", "openEMS",
    ]

    def __init__(self, config: InstallConfig, theme_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme_manager = theme_manager
        self.plan: InstallPlan | None = None
        self.tool_worker: ToolCheckWorker | None = None
        self.install_worker: InstallWorker | None = None
        self.executor: InstallExecutor | None = None
        self._tc_phase = "selection"
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
        self.tools_table.setColumnCount(4)
        self.tools_table.setHorizontalHeaderLabels(
            ["Tool", "Status", "Version", "Custom Path"]
        )
        for col in range(4):
            self.tools_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )
        self.tools_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tools_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.tools_table.hide()
        tools_lay.addWidget(self.tools_table)
        self.tools_group.setLayout(tools_lay)
        self.tools_group.hide()
        root.addWidget(self.tools_group)

        self.env_group = QGroupBox("Environment Variables")
        env_lay = QVBoxLayout()
        self.env_table = QTableWidget()
        self.env_table.verticalHeader().setVisible(False)
        self.env_table.setColumnCount(4)
        self.env_table.setHorizontalHeaderLabels(
            ["Variable", "Status", "Current Value", "Action"]
        )
        for col in [0, 2, 3]:
            self.env_table.horizontalHeader().setSectionResizeMode(
                col, QHeaderView.ResizeMode.Stretch
            )
        self.env_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.env_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.env_table.hide()
        env_lay.addWidget(self.env_table)
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
        self.install_log.hide()
        self.install_log.clear()
        self.install_result_label.hide()
        self.hint_label.hide()

    def _sync_tc_from_eda(self):
        eda_tools = set()
        for sim in self.config.simulators:
            eda_tools.add(sim.value)
            if sim == Simulator.XYCE:
                eda_tools.add("buildxyceplugin")
            elif sim == Simulator.GNUCAP:
                eda_tools.add("gnucap-mg-vams")
        for ed in self.config.schematic_editors:
            eda_tools.add(ed.value)
        for ed in self.config.layout_editors:
            eda_tools.add(ed.value)
        for tool, cb in self.tc_checks.items():
            base = tool.split("/")[0]
            if base in eda_tools or tool in eda_tools:
                cb.setChecked(True)

    def _configured_tools(self) -> list[str]:
        tools = set()
        for sim in self.config.simulators:
            if sim.value == "ngspice":
                tools.add("ngspice")
            elif sim.value == "Xyce":
                tools.add("Xyce")
                tools.add("buildxyceplugin")
            elif sim.value == "gnucap":
                tools.add("gnucap")
                tools.add("gnucap-mg-vams")
            tools.add("openvaf/openvaf-r")

        for ed in self.config.schematic_editors:
            tools.add(ed.value)
        for ed in self.config.layout_editors:
            tools.add(ed.value)

        tools.add("python3")
        tools.add("pip")
        return list(tools)

    def _extra_tools(self) -> list[str]:
        configured = {_canonical_tool_name(t) for t in self._configured_tools()}
        return [
            t for t in self.tc_checks
            if self.tc_checks[t].isChecked()
            and _canonical_tool_name(t) not in configured
        ]

    def show_tool_selection(self):
        self.reset_view()
        self._tc_phase = "selection"
        self.tc_section.show()
        self.tc_scroll.show()
        self._sync_tc_from_eda()
        self.status_label.hide()
        self.hint_label.setText("Select tools to check, then click Check.")
        self.hint_label.show()

        self.nav_state_changed.emit({
            "next_enabled": True,
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

        extra = self._extra_tools()
        self.tool_worker = ToolCheckWorker(self.config, extra)
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
        has_sim = len(self.config.simulators) > 0
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

    def _populate_tools(self, tools):
        self.tools_table.setRowCount(len(tools))
        self.tools_group.show()
        self.tools_table.show()
        for i, t in enumerate(tools):
            name_item = QTableWidgetItem(_tool_display_name(t.name))
            name_item.setData(Qt.UserRole, t)
            self.tools_table.setItem(i, 0, name_item)

            status_item = QTableWidgetItem(t.status.value)
            status_item.setForeground(self._get_status_color(t.status))
            self.tools_table.setItem(i, 1, status_item)

            self.tools_table.setItem(i, 2, QTableWidgetItem(t.version or "N/A"))

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
                        self.tools_table.setItem(r, 3, QTableWidgetItem(d))

                return cb

            def make_recheck_cb(r):
                def cb():
                    path_item = self.tools_table.item(r, 3)
                    custom_dir = path_item.text().strip() if path_item else ""
                    if not custom_dir or custom_dir == "---":
                        return
                    tool_info = self.tools_table.item(r, 0)
                    tool_obj = tool_info.data(Qt.UserRole) if tool_info else None
                    raw_tool_name = tool_obj.name if tool_obj else ""
                    if _canonical_tool_name(raw_tool_name) == "openvaf":
                        candidates = ["openvaf-r", "openvaf"]
                    else:
                        candidates = [raw_tool_name.split("/")[0]] if raw_tool_name else []

                    found_name = ""
                    for candidate in candidates:
                        bin_path = os.path.join(custom_dir, candidate)
                        if os.path.isfile(bin_path) and os.access(bin_path, os.X_OK):
                            found_name = candidate
                            break

                    if found_name:
                        ver = get_version(found_name) or "found"
                        self.tools_table.setItem(r, 1, QTableWidgetItem("OK"))
                        self.tools_table.item(r, 1).setForeground(
                            self.theme_manager.get_color("status_ok")
                        )
                        self.tools_table.setItem(r, 2, QTableWidgetItem(ver))
                    else:
                        try:
                            env = os.environ.copy()
                            env["PATH"] = custom_dir + ":" + env.get("PATH", "")
                            found = ""
                            for candidate in candidates:
                                result = subprocess.run(
                                    ["which", candidate],
                                    env=env,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL,
                                    text=True,
                                    timeout=5,
                                )
                                if result.returncode == 0:
                                    found = result.stdout.strip()
                                    break
                            if found:
                                self.tools_table.setItem(r, 1, QTableWidgetItem("OK"))
                                self.tools_table.item(r, 1).setForeground(
                                    self.theme_manager.get_color("status_ok")
                                )
                            else:
                                self.tools_table.setItem(r, 1, QTableWidgetItem("MISSING"))
                                self.tools_table.item(r, 1).setForeground(
                                    self.theme_manager.get_color("status_error")
                                )
                        except Exception:
                            pass

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
