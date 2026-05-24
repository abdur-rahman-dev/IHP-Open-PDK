from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QProgressBar,
    QGroupBox, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QColor

from installer.backend.models import (
    InstallPlan, ToolStatusEnum, EnvCheckResult, InstallConfig,
)
from installer.backend.checker import build_install_plan


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
    next_requested = Signal()
    back_requested = Signal()

    def __init__(self, config: InstallConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self.plan: InstallPlan | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.title = QLabel("Tool & Environment Check")
        self.title.setStyleSheet("font-size: 18px; font-weight: bold; color: #00509E;")
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
        self.result_label.setStyleSheet("font-size: 14px; font-weight: bold;")
        self.result_label.hide()
        root.addWidget(self.result_label)

        btn_lay = QHBoxLayout()
        self.back_btn = QPushButton("< Back")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_lay.addWidget(self.back_btn)
        btn_lay.addStretch()
        self.next_btn = QPushButton("View Plan >")
        self.next_btn.clicked.connect(self.next_requested.emit)
        self.next_btn.setEnabled(False)
        btn_lay.addWidget(self.next_btn)
        root.addLayout(btn_lay)

    def run_check(self):
        self.progress_bar.show()
        self.tools_table.hide()
        self.env_group.hide()
        self.result_label.hide()
        self.next_btn.setEnabled(False)
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
            self.result_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #C0392B;"
            )
        elif plan.has_warnings():
            self.result_label.setText("Completed with WARNINGS")
            self.result_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #E67E22;"
            )
        else:
            self.result_label.setText("All checks PASSED")
            self.result_label.setStyleSheet(
                "font-size: 14px; font-weight: bold; color: #228B22;"
            )
        self.result_label.show()
        self.next_btn.setEnabled(True)
        self.status_label.setText("Check complete.")

    def _populate_tools(self, tools):
        self.tools_table.setRowCount(len(tools))
        self.tools_table.show()
        for i, t in enumerate(tools):
            name_item = QTableWidgetItem(t.name)
            name_item.setData(Qt.UserRole, t)
            self.tools_table.setItem(i, 0, name_item)

            status_item = QTableWidgetItem(t.status.value)
            if t.status == ToolStatusEnum.OK:
                status_item.setForeground(QColor("#228B22"))
            elif t.status == ToolStatusEnum.WARNING:
                status_item.setForeground(QColor("#E67E22"))
            elif t.status == ToolStatusEnum.ERROR:
                status_item.setForeground(QColor("#C0392B"))
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
        for i, e in enumerate(env_checks):
            self.env_table.setItem(i, 0, QTableWidgetItem(e.variable))
            status = "OK" if e.is_set else "MISSING"
            item = QTableWidgetItem(status)
            if e.is_set:
                item.setForeground(QColor("#228B22"))
            else:
                item.setForeground(QColor("#E67E22"))
            self.env_table.setItem(i, 1, item)
            self.env_table.setItem(i, 2, QTableWidgetItem(e.action))

        self.env_table.resizeColumnsToContents()
