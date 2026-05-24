import os
from pathlib import Path

from PySide6.QtWidgets import QComboBox, QApplication
from PySide6.QtGui import QColor, QPalette
from PySide6.QtCore import Signal, QObject

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"

LIGHT_COLORS = {
    "brand": "#00509E",
    "brand_light": "#E8F0FE",
    "bg": "#FFFFFF",
    "bg_alt": "#F5F7FA",
    "surface": "#FFFFFF",
    "text": "#1A1A2E",
    "text_secondary": "#666666",
    "text_dim": "#999999",
    "border": "#D0D5DD",
    "border_light": "#E5E7EB",
    "status_ok": "#228B22",
    "status_warn": "#E67E22",
    "status_error": "#C0392B",
    "btn_bg": "#00509E",
    "btn_hover": "#003D7A",
    "btn_text": "#FFFFFF",
    "input_bg": "#FFFFFF",
    "input_border": "#D0D5DD",
    "table_header_bg": "#00509E",
    "table_header_text": "#FFFFFF",
    "table_alt_row": "#F5F7FA",
    "table_grid": "#E5E7EB",
    "group_bg": "#FFFFFF",
    "group_border": "#D0D5DD",
    "progress_bar": "#00509E",
    "separator": "#00509E",
    "scrollbar": "#C1C1C1",
    "scrollbar_hover": "#A0A0A0",
}

DARK_COLORS = {
    "brand": "#89B4FA",
    "brand_light": "#1E2940",
    "bg": "#1E1E2E",
    "bg_alt": "#252536",
    "surface": "#2A2A3C",
    "text": "#CDD6F4",
    "text_secondary": "#A6ADC8",
    "text_dim": "#6C7086",
    "border": "#45475A",
    "border_light": "#313244",
    "status_ok": "#A6E3A1",
    "status_warn": "#F9E2AF",
    "status_error": "#F38BA8",
    "btn_bg": "#89B4FA",
    "btn_hover": "#74C7EC",
    "btn_text": "#1E1E2E",
    "input_bg": "#313244",
    "input_border": "#45475A",
    "table_header_bg": "#313244",
    "table_header_text": "#CDD6F4",
    "table_alt_row": "#252536",
    "table_grid": "#45475A",
    "group_bg": "#2A2A3C",
    "group_border": "#45475A",
    "progress_bar": "#89B4FA",
    "separator": "#89B4FA",
    "scrollbar": "#45475A",
    "scrollbar_hover": "#585B70",
}

_THEMES = {
    "light": LIGHT_COLORS,
    "dark": DARK_COLORS,
}


def _load_qss(name: str) -> str:
    path = ASSETS_DIR / f"{name}.qss"
    if not path.exists():
        return ""
    with open(path, "r") as f:
        return f.read()


def _resolve_qss(template: str, colors: dict) -> str:
    qss = template
    for key, value in colors.items():
        qss = qss.replace(f"@{key}@", value)
    return qss


def detect_system_theme() -> str:
    env_theme = os.environ.get("COLOR_SCHEME", "").lower()
    if env_theme in ("light", "dark"):
        return env_theme

    gtk_theme = os.environ.get("GTK_THEME", "").lower()
    if "dark" in gtk_theme:
        return "dark"
    if gtk_theme:
        return "light"

    kde_session = os.environ.get("KDE_SESSION_VERSION", "")
    if kde_session:
        try:
            import subprocess
            result = subprocess.run(
                ["kreadconfig" + kde_session, "--group", "Colors", "--key", "Window"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=2,
            )
            if result.returncode == 0 and "dark" in result.stdout.lower():
                return "dark"
        except Exception:
            pass

    desktop = os.environ.get("XDG_CURRENT_DESKTOP", "").lower()
    if "gnome" in desktop:
        try:
            import subprocess
            result = subprocess.run(
                ["gsettings", "get", "org.gnome.desktop.interface", "color-scheme"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3,
            )
            if result.returncode == 0:
                val = result.stdout.strip().strip("'")
                if "dark" in val.lower():
                    return "dark"
                if "light" in val.lower() or val == "default":
                    return "light"
        except Exception:
            pass

    try:
        import subprocess
        result = subprocess.run(
            ["gsettings", "get", "org.gnome.desktop.interface", "gtk-theme"],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, timeout=3,
        )
        if result.returncode == 0 and "dark" in result.stdout.lower():
            return "dark"
    except Exception:
        pass

    return "light"


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, app: QApplication, initial: str = "system"):
        super().__init__()
        self.app = app
        self._current_theme = "light"
        self._current_mode = "system"
        self._qss_template_light = _load_qss("light")
        self._qss_template_dark = _load_qss("dark")

        if initial == "system":
            resolved = detect_system_theme()
        else:
            resolved = initial
        self._apply(resolved)

    def current_theme(self) -> str:
        return self._current_theme

    def get_color(self, semantic: str) -> QColor:
        colors = _THEMES.get(self._current_theme, LIGHT_COLORS)
        hex_val = colors.get(semantic, "#000000")
        return QColor(hex_val)

    def create_combo(self, parent=None) -> QComboBox:
        combo = QComboBox()
        combo.addItems(["System", "Light", "Dark"])
        mode_map = {"system": 0, "light": 1, "dark": 2}
        combo.setCurrentIndex(mode_map.get(self._current_mode, 0))
        combo.setFixedWidth(100)
        combo.currentIndexChanged.connect(self._on_combo_changed)
        return combo

    def set_theme(self, mode: str):
        if mode == "system":
            resolved = detect_system_theme()
        else:
            resolved = mode
        self._current_mode = mode
        self._apply(resolved)

    def _on_combo_changed(self, index: int):
        modes = ["system", "light", "dark"]
        self.set_theme(modes[index])

    def _apply(self, theme_name: str):
        self._current_theme = theme_name
        colors = _THEMES.get(theme_name, LIGHT_COLORS)

        if theme_name == "dark":
            qss = _resolve_qss(self._qss_template_dark, colors)
        else:
            qss = _resolve_qss(self._qss_template_light, colors)

        self.app.setStyleSheet(qss)

        palette = QPalette()
        palette.setColor(QPalette.ColorRole.Window, QColor(colors["bg"]))
        palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
        palette.setColor(QPalette.ColorRole.Base, QColor(colors["input_bg"]))
        palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["bg_alt"]))
        palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
        palette.setColor(QPalette.ColorRole.Button, QColor(colors["surface"]))
        palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
        palette.setColor(QPalette.ColorRole.BrightText, QColor(colors["text"]))
        palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["brand"]))
        palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["btn_text"]))
        palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["surface"]))
        palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["text_dim"]))
        self.app.setPalette(palette)

        self.theme_changed.emit(theme_name)
