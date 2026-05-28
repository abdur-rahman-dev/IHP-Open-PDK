import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QRadioButton,
    QCheckBox, QButtonGroup, QLineEdit, QPushButton, QGroupBox,
    QFileDialog, QGridLayout,
)
from PySide6.QtCore import Qt, Signal

from installer.backend.models import (
    InstallConfig, PDKChoice, Simulator, SchematicEditor,
    LayoutEditor, InstallMode,
)

PDK_OPTIONS = [
    ("ihp-sg13g2", "SG13G2", True),
    ("ihp-sg13cmos5l", "SG13CMOS5L", False),
]


class ChoicePage(QWidget):
    skip_tool_check_changed = Signal(bool)

    PDK_DIR_MAP = {
        "ihp-sg13g2": "ihp-sg13g2",
        "ihp-sg13cmos5l": "ihp-sg13cmos5l",
    }

    def __init__(self, config: InstallConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._base_dir = ""
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        row = 0

        pdk_group = QGroupBox("PDK")
        pdk_lay = QHBoxLayout()
        self.pdk_btn_group = QButtonGroup(self)
        for i, (val, label, default) in enumerate(PDK_OPTIONS):
            rb = QRadioButton(label)
            rb.setChecked(default)
            rb.setProperty("pdk_value", val)
            self.pdk_btn_group.addButton(rb, i)
            pdk_lay.addWidget(rb)
            if default:
                rb.setChecked(True)
        self.pdk_btn_group.buttonClicked.connect(self._on_pdk_changed)
        pdk_group.setLayout(pdk_lay)
        grid.addWidget(pdk_group, row, 0, 1, 2)
        row += 1

        mode_group = QGroupBox("Mode")
        mode_lay = QHBoxLayout()
        self.mode_btn_group = QButtonGroup(self)
        self.mode_new = QRadioButton("Install")
        self.mode_new.setChecked(True)
        self.mode_change = QRadioButton("Change PDK")
        self.mode_btn_group.addButton(self.mode_new, 0)
        self.mode_btn_group.addButton(self.mode_change, 1)
        mode_lay.addWidget(self.mode_new)
        mode_lay.addWidget(self.mode_change)
        mode_group.setLayout(mode_lay)
        grid.addWidget(mode_group, row, 0, 1, 2)
        row += 1

        ic_group = QGroupBox("Install Config")
        ic_lay = QVBoxLayout()
        self.compile_va_cb = QCheckBox("Compile Verilog-A")
        self.compile_va_cb.setChecked(True)
        self.mode_btn_group.buttonClicked.connect(self._on_mode_changed)
        ic_lay.addWidget(self.compile_va_cb)
        self.skip_tool_check_cb = QCheckBox("Skip tool check")
        self.skip_tool_check_cb.setChecked(False)
        self.skip_tool_check_cb.toggled.connect(self.skip_tool_check_changed.emit)
        ic_lay.addWidget(self.skip_tool_check_cb)
        ic_group.setLayout(ic_lay)
        grid.addWidget(ic_group, row, 0, 1, 2)
        row += 1

        eda_group = QGroupBox("EDA Config")
        eda_grid = QGridLayout()
        eda_grid.setSpacing(8)

        all_items = []
        self.sim_checks = {}
        for sim in Simulator:
            all_items.append(("sim", sim))
        self.sch_checks = {}
        for ed in SchematicEditor:
            all_items.append(("sch", ed))
        self.lay_checks = {}
        for ed in LayoutEditor:
            if ed == LayoutEditor.MAGIC:
                continue
            all_items.append(("lay", ed))

        cols = 3
        for i, (group, item) in enumerate(all_items):
            r, c = divmod(i, cols)
            cb = QCheckBox(item.value)
            if group == "sim":
                cb.setChecked(item == Simulator.NGSPICE)
                cb.setProperty("sim_value", item)
                self.sim_checks[item] = cb
            elif group == "sch":
                cb.setChecked(item == SchematicEditor.XSCHEM)
                cb.setProperty("sch_value", item)
                self.sch_checks[item] = cb
            else:
                cb.setChecked(item == LayoutEditor.KLAYOUT)
                cb.setProperty("lay_value", item)
                self.lay_checks[item] = cb
            eda_grid.addWidget(cb, r, c)

        eda_group.setLayout(eda_grid)
        grid.addWidget(eda_group, row, 0, 1, 2)
        row += 1

        dir_group = QGroupBox("Installation Directory")
        dir_lay = QHBoxLayout()
        self.dir_input = QLineEdit()
        self.dir_input.setPlaceholderText("Leave empty to use current PDK location")
        dir_lay.addWidget(self.dir_input, 1)
        self.dir_browse = QPushButton("Browse...")
        self.dir_browse.setObjectName("browse_btn")
        self.dir_browse.clicked.connect(self._on_browse)
        dir_lay.addWidget(self.dir_browse)
        dir_group.setLayout(dir_lay)
        grid.addWidget(dir_group, row, 0, 1, 2)
        row += 1

        root.addLayout(grid)
        root.addStretch()

    def set_base_dir(self, base_dir: str):
        self._base_dir = base_dir
        self._update_dir_for_pdk()

    def _get_selected_pdk(self) -> str:
        for btn in self.pdk_btn_group.buttons():
            if btn.isChecked():
                return btn.property("pdk_value")
        return "ihp-sg13g2"

    def _on_pdk_changed(self, btn):
        self._update_dir_for_pdk()

    def _on_mode_changed(self, btn):
        self.compile_va_cb.setChecked(self.mode_new.isChecked())

    def _update_dir_for_pdk(self):
        if not self._base_dir:
            return
        pdk = self._get_selected_pdk()
        subdir = self.PDK_DIR_MAP.get(pdk, pdk)
        self.dir_input.setText(os.path.join(self._base_dir, subdir))

    def _on_browse(self):
        d = QFileDialog.getExistingDirectory(self, "Select Installation Directory")
        if d:
            self.dir_input.setText(d)

    def get_config(self) -> InstallConfig:
        for btn in self.pdk_btn_group.buttons():
            if btn.isChecked():
                self.config.pdk = PDKChoice(btn.property("pdk_value"))
                break

        self.config.simulators = [
            sim for sim, cb in self.sim_checks.items() if cb.isChecked()
        ]

        self.config.schematic_editors = [
            ed for ed, cb in self.sch_checks.items() if cb.isChecked()
        ]

        self.config.layout_editors = [
            ed for ed, cb in self.lay_checks.items() if cb.isChecked()
        ]

        self.config.install_mode = (
            InstallMode.NEW if self.mode_new.isChecked() else InstallMode.CHANGE
        )

        self.config.install_dir = (
            self.dir_input.text().strip() or None
        )

        self.config.compile_verilog_a = self.compile_va_cb.isChecked()
        self.config.skip_tool_check = self.skip_tool_check_cb.isChecked()

        return self.config
