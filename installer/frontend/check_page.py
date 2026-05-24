from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QGroupBox, QTextEdit, QMessageBox,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from installer.backend.models import (
    InstallPlan, ToolStatusEnum, EnvCheckResult, InstallConfig,
    ExecStepStatus,
)
from installer.backend.checker import build_install_plan
from installer.backend.executor import InstallExecutor


class CheckWorker(QThread):
    progress = Signal(str)
    done = Signal(object)

    def __init__(self, config: InstallConfig):
        super().__init__()
        self.config = config

    def run(self):
        self.progress.emit("Checking tools...")
        plan = build_install_plan(self.config)
        self.progress.emit("Check complete.")
        self.done.emit(plan)


class CheckPage(QWidget):
    back_requested = Signal()

    def __init__(self, config: InstallConfig, theme_manager, parent=None):
        super().__init__(parent)
        self.config = config
        self.theme_manager = theme_manager
        self.plan: InstallPlan | None = None
        self.executor: InstallExecutor | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.title = QLabel("Tool & Environment Check")
        self.title.setObjectName("page_title")
        self.title.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Checking...")
        root.addWidget(self.progress_bar)

        self.status_label = QLabel("Preparing to check tools...")
        self.status_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.status_label)

        self.tools_table = QTableWidget()
        self.tools_table.setColumnCount(4)
        self.tools_table.setHorizontalHeaderLabels(
            ["Tool", "Status", "Version", "Notes"]
        )
        self.tools_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.tools_table.horizontalHeader().setSectionResizeMode(
            3, QHeaderView.ResizeMode.Stretch
        )
        self.tools_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tools_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.tools_table.hide()
        root.addWidget(self.tools_table)

        self.env_group = QGroupBox("Environment Variables")
        env_lay = QVBoxLayout()
        self.env_table = QTableWidget()
        self.env_table.setColumnCount(3)
        self.env_table.setHorizontalHeaderLabels(
            ["Variable", "Status", "Action"]
        )
        self.env_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Stretch
        )
        self.env_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
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

        self.result_label = QLabel("")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.hide()
        root.addWidget(self.result_label)

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

        btn_lay = QHBoxLayout()
        self.back_btn = QPushButton("< Back")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_lay.addWidget(self.back_btn)
        btn_lay.addStretch()
        self.install_btn = QPushButton("Install")
        self.install_btn.clicked.connect(self._on_install)
        self.install_btn.setEnabled(False)
        btn_lay.addWidget(self.install_btn)
        root.addLayout(btn_lay)

    def run_check(self):
        self.progress_bar.show()
        self.tools_table.hide()
        self.env_group.hide()
        self.result_label.hide()
        self.exec_log.hide()
        self.install_result_label.hide()
        self.install_btn.setEnabled(False)
        self.back_btn.setEnabled(True)
        self.status_label.setText("Running tool checks...")

        self.worker = CheckWorker(self.config)
        self.worker.progress.connect(self._on_progress)
        self.worker.done.connect(self._on_done)
        self.worker.start()

    def _on_progress(self, msg):
        self.status_label.setText(msg)

    def _on_done(self, plan: InstallPlan):
        self.plan = plan
        self.progress_bar.hide()
        self._populate_tools(plan.tools)
        self._populate_env(plan.env_checks)

        if plan.has_errors():
            self.result_label.setText("ERRORS found - see details below")
            self.result_label.setObjectName("result_error")
            self.install_btn.setEnabled(False)
        elif plan.has_warnings():
            self.result_label.setText("Completed with WARNINGS")
            self.result_label.setObjectName("result_warn")
            self.install_btn.setEnabled(True)
        else:
            self.result_label.setText("All checks PASSED")
            self.result_label.setObjectName("result_ok")
            self.install_btn.setEnabled(True)
        self.result_label.setStyle(self.result_label.style())
        self.result_label.show()
        self.status_label.setText("Check complete. Click Install to proceed.")

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
        self.tools_table.show()
        for i, t in enumerate(tools):
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t)
            self.tools_table.setItem(i, 0, name_item)

            status_item = QTableWidgetItem(t.status.value)
            status_item.setForeground(self._get_status_color(t.status))
            self.tools_table.setItem(i, 1, status_item)

            self.tools_table.setItem(i, 2, QTableWidgetItem(t.version or "---"))
            self.tools_table.setItem(i, 3, QTableWidgetItem(t.message))

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
            self.env_table.setItem(i, 2, QTableWidgetItem(e.action))

        self.env_table.resizeColumnsToContents()
