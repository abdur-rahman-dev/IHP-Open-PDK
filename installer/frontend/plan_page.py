import os
import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog, QProgressBar, QTableWidget,
    QTableWidgetItem, QHeaderView,
)
from PySide6.QtCore import Qt, Signal

from installer.backend.models import InstallPlan, ExecStepStatus
from installer.backend.executor import InstallExecutor


class PlanPage(QWidget):
    back_requested = Signal()

    def __init__(self, theme_manager, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.plan: InstallPlan | None = None
        self.executor: InstallExecutor | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.title = QLabel("Installation Plan")
        self.title.setObjectName("page_title")
        self.title.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title)

        self.summary = QLabel(
            "Review the installation plan below. Click 'Save Plan' to export as Markdown, "
            "or 'Install' to execute."
        )
        self.summary.setObjectName("subtitle")
        self.summary.setAlignment(Qt.AlignCenter)
        root.addWidget(self.summary)

        self.plan_view = QTextEdit()
        self.plan_view.setReadOnly(True)
        font = self.plan_view.font()
        font.setFamily("monospace")
        font.setPointSize(10)
        self.plan_view.setFont(font)
        root.addWidget(self.plan_view, 1)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        self.progress_bar.hide()
        root.addWidget(self.progress_bar)

        self.exec_log = QTextEdit()
        self.exec_log.setReadOnly(True)
        self.exec_log.setMaximumHeight(120)
        log_font = self.exec_log.font()
        log_font.setFamily("monospace")
        log_font.setPointSize(9)
        self.exec_log.setFont(log_font)
        self.exec_log.hide()
        root.addWidget(self.exec_log)

        self.result_label = QLabel("")
        self.result_label.setObjectName("result_ok")
        self.result_label.setAlignment(Qt.AlignCenter)
        self.result_label.hide()
        root.addWidget(self.result_label)

        btn_lay = QHBoxLayout()
        self.back_btn = QPushButton("< Back")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_lay.addWidget(self.back_btn)
        btn_lay.addStretch()
        self.save_btn = QPushButton("Save Plan (.md)")
        self.save_btn.clicked.connect(self._on_save)
        btn_lay.addWidget(self.save_btn)
        self.install_btn = QPushButton("Install")
        self.install_btn.clicked.connect(self._on_install)
        btn_lay.addWidget(self.install_btn)
        root.addLayout(btn_lay)

    def set_plan(self, plan: InstallPlan):
        self.plan = plan
        md = plan.to_markdown()
        html = self._md_to_html(md)
        self.plan_view.setHtml(html)

        has_errors = plan.has_errors()
        self.install_btn.setEnabled(not has_errors)
        if has_errors:
            self.summary.setText("Plan has errors. Fix them before installing.")

    def _on_install(self):
        if not self.plan:
            return
        from PySide6.QtWidgets import QMessageBox
        reply = QMessageBox.question(
            self, "Confirm Installation",
            "This will execute the installation plan.\n\nDo you want to proceed?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        self.install_btn.setEnabled(False)
        self.back_btn.setEnabled(False)
        self.save_btn.setEnabled(False)
        self.progress_bar.show()
        self.progress_bar.setValue(0)
        self.exec_log.show()
        self.exec_log.clear()
        self.result_label.hide()
        self.summary.setText("Installing... please wait.")

        self.executor = InstallExecutor(self.plan)
        self.executor.step_started.connect(self._on_step_started)
        self.executor.step_finished.connect(self._on_step_finished)
        self.executor.all_done.connect(self._on_all_done)
        self.executor.log_line.connect(self._on_log)
        self.executor.start()

    def _on_step_started(self, idx: int, label: str):
        self.exec_log.append(f"[{idx+1}] {label}...")
        self.progress_bar.setFormat(f"Step {idx+1}: {label}")

    def _on_step_finished(self, idx: int, label: str, ok: bool):
        status = "OK" if ok else "FAILED"
        color = "green" if ok else "red"
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

    def _on_all_done(self, success: bool):
        self.install_btn.setEnabled(True)
        self.back_btn.setEnabled(True)
        self.save_btn.setEnabled(True)
        self.progress_bar.setValue(100)

        if success:
            self.result_label.setText("Installation completed successfully!")
            self.result_label.setObjectName("result_ok")
            self.summary.setText("Installation complete. You may save the plan or go back.")
        else:
            self.result_label.setText("Installation completed with errors. See log above.")
            self.result_label.setObjectName("result_error")
            self.summary.setText("Some steps failed. Check the log for details.")

        self.result_label.setStyle(self.result_label.style())
        self.result_label.show()
        self.progress_bar.setFormat("Done" if success else "Done (with errors)")

    def _on_save(self):
        if not self.plan:
            return
        default_dir = os.path.join(os.path.expanduser("~"), "Tasks", "Task3")
        os.makedirs(default_dir, exist_ok=True)
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = f"install_plan_{timestamp}.md"
        default_path = os.path.join(default_dir, default_name)

        path, _ = QFileDialog.getSaveFileName(
            self, "Save Installation Plan", default_path,
            "Markdown Files (*.md);;All Files (*)",
        )
        if path:
            md = self.plan.to_markdown()
            with open(path, "w") as f:
                f.write(md)
            self.save_btn.setText("Saved!")

    def _md_to_html(self, md: str) -> str:
        colors = {
            "brand": self.theme_manager.get_color("brand").name(),
            "text": self.theme_manager.get_color("text").name(),
            "bg": self.theme_manager.get_color("surface").name(),
            "bg_alt": self.theme_manager.get_color("bg_alt").name(),
            "border": self.theme_manager.get_color("border").name(),
        }

        lines = md.split("\n")
        html_parts = [
            f"<style>"
            f"body {{ color: {colors['text']}; background: {colors['bg']}; font-family: monospace; }}"
            f"table {{ border-collapse: collapse; width: 100%; }}"
            f"th {{ background-color: {colors['brand']}; color: white; padding: 6px 8px; text-align: left; }}"
            f"td {{ padding: 4px 8px; border-bottom: 1px solid {colors['border']}; }}"
            f"tr:nth-child(even) {{ background-color: {colors['bg_alt']}; }}"
            f"h2 {{ color: {colors['brand']}; }}"
            f"h3 {{ color: {colors['brand']}; }}"
            f"</style>",
        ]
        in_list = False

        for line in lines:
            stripped = line.strip()
            if stripped.startswith("# "):
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                html_parts.append(f"<h2>{stripped[2:]}</h2>")
            elif stripped.startswith("## "):
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                html_parts.append(f"<h3>{stripped[3:]}</h3>")
            elif stripped.startswith("**") and stripped.endswith("**"):
                html_parts.append(f"<p><b>{stripped[2:-2]}</b></p>")
            elif stripped.startswith("|") and "---" in stripped:
                continue
            elif stripped.startswith("|"):
                cells = [c.strip() for c in stripped.split("|")[1:-1]]
                tag = "td"
                row_html = "<tr>"
                for cell in cells:
                    row_html += f"<{tag}>{cell}</{tag}>"
                row_html += "</tr>"
                html_parts.append(row_html)
            elif stripped.startswith("- "):
                if not in_list:
                    html_parts.append("<ul>")
                    in_list = True
                html_parts.append(f"<li>{stripped[2:]}</li>")
            elif stripped and stripped[0].isdigit() and ". " in stripped:
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                num, text = stripped.split(". ", 1)
                html_parts.append(f"<p>{num}. {text}</p>")
            elif stripped:
                if in_list:
                    html_parts.append("</ul>")
                    in_list = False
                html_parts.append(f"<p>{stripped}</p>")

        if in_list:
            html_parts.append("</ul>")

        return "".join(html_parts)
