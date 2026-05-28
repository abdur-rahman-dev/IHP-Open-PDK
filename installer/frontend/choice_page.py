import os

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QCheckBox, QButtonGroup, QLineEdit, QPushButton, QGroupBox,
    QFileDialog, QGridLayout, QScrollArea,
)
from PySide6.QtCore import Qt

from installer.backend.models import (
    InstallConfig, PDKChoice, Simulator, SchematicEditor,
    LayoutEditor, InstallMode,
)

PDK_OPTIONS = [
    ("ihp-sg13g2", "SG13G2 (130nm)", True),
    ("ihp-sg13cmos5l", "SG13CMOS5L", False),
]


class ChoicePage(QWidget):
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

        pdk_group = QGroupBox("PDK Selection")
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

        eda_group = QGroupBox("Config EDA")
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

        tc_group = QGroupBox("Tool Check")
        tc_lay = QVBoxLayout()
        self.tc_enable = QCheckBox("Requirement check for EDA tool")
        self.tc_enable.setChecked(False)
        self.tc_enable.toggled.connect(self._on_tc_toggled)
        tc_lay.addWidget(self.tc_enable)

        tc_tools_inner = QWidget()
        tc_tools_grid = QGridLayout()
        tc_tools_grid.setContentsMargins(20, 4, 4, 4)
        tc_tools_grid.setSpacing(4)
        self.tc_checks = {}
        all_tools = [
            "python3", "pip", "openvaf/openvaf-r",
            "buildxyceplugin", "gnucap-mg-vams", "ngspice",
            "Xyce", "gnucap", "xschem",
            "qucs-s", "klayout", "magic",
            "netgen", "openEMS",
        ]
        for i, tool in enumerate(all_tools):
            cb = QCheckBox(tool)
            cb.setChecked(False)
            self.tc_checks[tool] = cb
            r, c = divmod(i, 3)
            tc_tools_grid.addWidget(cb, r, c)
        tc_tools_inner.setLayout(tc_tools_grid)

        tc_scroll = QScrollArea()
        tc_scroll.setWidget(tc_tools_inner)
        tc_scroll.setWidgetResizable(True)
        tc_scroll.setMaximumHeight(150)
        tc_scroll.hide()
        self.tc_tools_widget = tc_scroll
        tc_lay.addWidget(tc_scroll)
        tc_group.setLayout(tc_lay)
        grid.addWidget(tc_group, row, 0, 1, 2)
        row += 1

        ic_group = QGroupBox("Install Config")
        ic_lay = QHBoxLayout()
        self.compile_va_cb = QCheckBox("Compile Verilog-A")
        self.compile_va_cb.setChecked(True)
        self.mode_btn_group.buttonClicked.connect(self._on_mode_changed)
        ic_lay.addWidget(self.compile_va_cb)
        ic_lay.addStretch()
        ic_group.setLayout(ic_lay)
        grid.addWidget(ic_group, row, 0, 1, 2)
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

    def _on_tc_toggled(self, checked):
        self.tc_tools_widget.setVisible(checked)
        if checked:
            self._sync_tc_from_eda()

    def _sync_tc_from_eda(self):
        eda_tools = set()
        for sim, cb in self.sim_checks.items():
            if cb.isChecked():
                eda_tools.add(sim.value)
                if sim == Simulator.NGSPICE:
                    pass
                elif sim == Simulator.XYCE:
                    eda_tools.add("buildxyceplugin")
                elif sim == Simulator.GNUCAP:
                    eda_tools.add("gnucap-mg-vams")
        for ed, cb in self.sch_checks.items():
            if cb.isChecked():
                eda_tools.add(ed.value)
        for ed, cb in self.lay_checks.items():
            if cb.isChecked():
                eda_tools.add(ed.value)
        for tool, cb in self.tc_checks.items():
            base = tool.split("/")[0]
            if base in eda_tools or tool in eda_tools:
                cb.setChecked(True)

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

        self.config.check_tools = self.tc_enable.isChecked()
        self.config.tools_to_check = [
            t for t, cb in self.tc_checks.items() if cb.isChecked()
        ]
        self.config.compile_verilog_a = self.compile_va_cb.isChecked()

        return self.config
