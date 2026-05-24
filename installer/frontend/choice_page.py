from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QCheckBox, QButtonGroup, QLineEdit, QPushButton, QGroupBox,
    QFileDialog, QGridLayout,
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
    def __init__(self, config: InstallConfig, parent=None):
        super().__init__(parent)
        self.config = config
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

        eda_group = QGroupBox("EDA Configuration")
        eda_lay = QVBoxLayout()
        eda_lay.setSpacing(6)

        sim_inner = QHBoxLayout()
        sim_label = QLabel("Simulators:")
        sim_label.setFixedWidth(120)
        sim_inner.addWidget(sim_label)
        self.sim_checks = {}
        for sim in Simulator:
            cb = QCheckBox(sim.value)
            cb.setChecked(sim == Simulator.NGSPICE)
            cb.setProperty("sim_value", sim)
            self.sim_checks[sim] = cb
            sim_inner.addWidget(cb)
        sim_inner.addStretch()
        eda_lay.addLayout(sim_inner)

        sch_inner = QHBoxLayout()
        sch_label = QLabel("Schematic Editor:")
        sch_label.setFixedWidth(120)
        sch_inner.addWidget(sch_label)
        self.sch_checks = {}
        for ed in SchematicEditor:
            cb = QCheckBox(ed.value)
            cb.setChecked(ed == SchematicEditor.XSCHEM)
            cb.setProperty("sch_value", ed)
            self.sch_checks[ed] = cb
            sch_inner.addWidget(cb)
        sch_inner.addStretch()
        eda_lay.addLayout(sch_inner)

        lay_inner = QHBoxLayout()
        lay_label = QLabel("Layout Editor:")
        lay_label.setFixedWidth(120)
        lay_inner.addWidget(lay_label)
        self.lay_checks = {}
        for ed in LayoutEditor:
            cb = QCheckBox(ed.value)
            cb.setChecked(ed == LayoutEditor.KLAYOUT)
            cb.setProperty("lay_value", ed)
            self.lay_checks[ed] = cb
            lay_inner.addWidget(cb)
        lay_inner.addStretch()
        eda_lay.addLayout(lay_inner)

        eda_group.setLayout(eda_lay)
        grid.addWidget(eda_group, row, 0, 1, 2)
        row += 1

        tc_group = QGroupBox("Tool Check")
        tc_lay = QVBoxLayout()
        self.tc_enable = QCheckBox("Check EDA tools requirement")
        self.tc_enable.setChecked(False)
        self.tc_enable.toggled.connect(self._on_tc_toggled)
        tc_lay.addWidget(self.tc_enable)

        tc_tools_widget = QWidget()
        tc_tools_lay = QVBoxLayout()
        tc_tools_lay.setContentsMargins(20, 4, 4, 4)
        tc_tools_lay.setSpacing(4)
        self.tc_checks = {}
        all_tools = [
            "openvaf/openvaf-r", "ngspice", "Xyce", "buildxyceplugin",
            "gnucap", "gnucap-mg-vams", "xschem", "qucs-s",
            "klayout", "magic", "python3", "pip",
        ]
        for tool in all_tools:
            cb = QCheckBox(tool)
            cb.setChecked(False)
            self.tc_checks[tool] = cb
            tc_tools_lay.addWidget(cb)
        tc_tools_widget.setLayout(tc_tools_lay)
        tc_tools_widget.hide()
        self.tc_tools_widget = tc_tools_widget
        tc_lay.addWidget(tc_tools_widget)
        tc_group.setLayout(tc_lay)
        grid.addWidget(tc_group, row, 0, 1, 2)
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

    def _on_pdk_changed(self, btn):
        pass

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

        return self.config
