from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton,
    QCheckBox, QButtonGroup, QLineEdit, QPushButton, QGroupBox,
    QFileDialog, QGridLayout, QComboBox,
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
        root.setSpacing(16)

        title = QLabel("PDK Installer Configuration")
        title.setObjectName("page_title")
        title.setAlignment(Qt.AlignCenter)
        root.addWidget(title)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(12)
        row = 0

        pdk_group = QGroupBox("PDK Selection (select one)")
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

        sim_group = QGroupBox("Simulators (select one or more)")
        sim_lay = QHBoxLayout()
        self.sim_checks = {}
        for sim in Simulator:
            cb = QCheckBox(sim.value)
            cb.setChecked(sim == Simulator.NGSPICE)
            cb.setProperty("sim_value", sim)
            self.sim_checks[sim] = cb
            sim_lay.addWidget(cb)
        sim_group.setLayout(sim_lay)
        grid.addWidget(sim_group, row, 0, 1, 2)
        row += 1

        sch_group = QGroupBox("Schematic Editor (select one or both)")
        sch_lay = QHBoxLayout()
        self.sch_checks = {}
        for ed in SchematicEditor:
            cb = QCheckBox(ed.value)
            cb.setChecked(ed == SchematicEditor.XSCHEM)
            cb.setProperty("sch_value", ed)
            self.sch_checks[ed] = cb
            sch_lay.addWidget(cb)
        sch_group.setLayout(sch_lay)
        grid.addWidget(sch_group, row, 0, 1, 2)
        row += 1

        lay_group = QGroupBox("Layout Editor (select one or both)")
        lay_lay = QHBoxLayout()
        self.lay_checks = {}
        for ed in LayoutEditor:
            cb = QCheckBox(ed.value)
            cb.setChecked(ed == LayoutEditor.KLAYOUT)
            cb.setProperty("lay_value", ed)
            self.lay_checks[ed] = cb
            lay_lay.addWidget(cb)
        lay_group.setLayout(lay_lay)
        grid.addWidget(lay_group, row, 0, 1, 2)
        row += 1

        mode_group = QGroupBox("Install Mode")
        mode_lay = QHBoxLayout()
        self.mode_btn_group = QButtonGroup(self)
        self.mode_new = QRadioButton("New Installation")
        self.mode_new.setChecked(True)
        self.mode_change = QRadioButton("Change PDK")
        self.mode_btn_group.addButton(self.mode_new, 0)
        self.mode_btn_group.addButton(self.mode_change, 1)
        mode_lay.addWidget(self.mode_new)
        mode_lay.addWidget(self.mode_change)

        mode_note = QLabel(
            "'New' runs full tool checks.\n'Change PDK' skips tool checks unless tools are marked for re-check."
        )
        mode_note.setObjectName("dim_note")
        mode_note.setWordWrap(True)
        mode_lay.addWidget(mode_note)
        mode_group.setLayout(mode_lay)
        grid.addWidget(mode_group, row, 0, 1, 2)
        row += 1

        dir_group = QGroupBox("Installation Directory (Optional)")
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

        return self.config
