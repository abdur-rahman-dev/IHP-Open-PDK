import os
import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextEdit, QFileDialog,
)
from PySide6.QtCore import Qt, Signal

from installer.backend.models import InstallPlan


class PlanPage(QWidget):
    back_requested = Signal()

    def __init__(self, theme_manager, parent=None):
        super().__init__(parent)
        self.theme_manager = theme_manager
        self.plan: InstallPlan | None = None
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        self.title = QLabel("Installation Plan")
        self.title.setObjectName("page_title")
        self.title.setAlignment(Qt.AlignCenter)
        root.addWidget(self.title)

        summary = QLabel(
            "Review the installation plan below. Click 'Save Plan' to export as Markdown."
        )
        summary.setObjectName("subtitle")
        summary.setAlignment(Qt.AlignCenter)
        root.addWidget(summary)

        self.plan_view = QTextEdit()
        self.plan_view.setReadOnly(True)
        font = self.plan_view.font()
        font.setFamily("monospace")
        font.setPointSize(10)
        self.plan_view.setFont(font)
        root.addWidget(self.plan_view, 1)

        btn_lay = QHBoxLayout()
        self.back_btn = QPushButton("< Back")
        self.back_btn.clicked.connect(self.back_requested.emit)
        btn_lay.addWidget(self.back_btn)
        btn_lay.addStretch()
        self.save_btn = QPushButton("Save Plan (.md)")
        self.save_btn.clicked.connect(self._on_save)
        btn_lay.addWidget(self.save_btn)
        root.addLayout(btn_lay)

    def set_plan(self, plan: InstallPlan):
        self.plan = plan
        md = plan.to_markdown()
        html = self._md_to_html(md)
        self.plan_view.setHtml(html)

    def _md_to_html(self, md: str) -> str:
        colors = {
            "brand": self.theme_manager.get_color("brand").name(),
            "text": self.theme_manager.get_color("text").name(),
            "bg": self.theme_manager.get_color("surface").name(),
            "bg_alt": self.theme_manager.get_color("bg_alt").name(),
            "border": self.theme_manager.get_color("border").name(),
            "status_ok": self.theme_manager.get_color("status_ok").name(),
            "status_warn": self.theme_manager.get_color("status_warn").name(),
            "status_error": self.theme_manager.get_color("status_error").name(),
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
