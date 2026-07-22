import os
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QRadioButton,
    QCheckBox, QButtonGroup, QLineEdit, QPushButton, QGroupBox,
    QFileDialog, QGridLayout, QLabel, QComboBox,
)
from PySide6.QtCore import Qt, Signal

from installer.backend.models import (
    InstallConfig, PDKChoice, Simulator, SchematicEditor,
    LayoutEditor, InstallMode, PDKSourceType, GitHubSourceMode, detect_installer_root,
)
from installer.backend.pdk_registry import PDK_DEFINITIONS, get_pdk_definition
from installer.backend.tool_registry import get_tool_definition

PDK_OPTIONS = [
    (pdk.id, pdk.label, pdk.id == PDKChoice.SG13G2.value)
    for pdk in PDK_DEFINITIONS
]


class ChoicePage(QWidget):
    config_changed = Signal()

    PDK_DIR_MAP = {
        "ihp-sg13g2": "ihp-sg13g2",
        "ihp-sg13cmos5l": "ihp-sg13cmos5l",
    }

    def __init__(self, config: InstallConfig, parent=None):
        super().__init__(parent)
        self.config = config
        self._base_dir = ""
        self._script_root = detect_installer_root()
        self._build_ui()
        self._set_default_source_root_for_mode()

    def reset_to_defaults(self):
        for btn in self.pdk_btn_group.buttons():
            if btn.property("pdk_value") == PDKChoice.SG13G2.value:
                btn.setChecked(True)
                break
        self.mode_new.setChecked(True)
        self.mode_change.setChecked(False)
        self.compile_va_cb.setChecked(True)
        self.source_local.setChecked(True)
        self.source_github.setChecked(False)
        self.github_branch_radio.setChecked(True)
        self.github_commit_radio.setChecked(False)
        self.github_commit_input.clear()
        self.fetch_sg13g2_cb.setChecked(False)
        self.override_sg13g2_cb.setChecked(False)
        self._update_github_branch_choices()
        self._set_default_source_root_for_mode(force=True)

        for sim, cb in self.sim_checks.items():
            cb.setChecked(sim == Simulator.NGSPICE)
        for ed, cb in self.sch_checks.items():
            cb.setChecked(ed == SchematicEditor.XSCHEM)
        for ed, cb in self.lay_checks.items():
            cb.setChecked(ed == LayoutEditor.KLAYOUT)

        self._refresh_eda_visibility()
        self.set_source_status(True, "")
        self._update_dir_for_pdk()
        self.config_changed.emit()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setSpacing(12)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
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
        grid.addWidget(pdk_group, row, 0)

        source_group = QGroupBox("PDK Source")
        source_grid = QGridLayout()
        source_grid.setHorizontalSpacing(10)
        source_grid.setVerticalSpacing(8)

        self.source_btn_group = QButtonGroup(self)
        self.source_local = QRadioButton("From Local")
        self.source_github = QRadioButton("From GitHub")
        self.source_local.setChecked(True)
        self.source_btn_group.addButton(self.source_local, 0)
        self.source_btn_group.addButton(self.source_github, 1)
        source_top = QHBoxLayout()
        source_top.setSpacing(24)
        source_top.addWidget(self.source_local, 1)
        source_top.addWidget(self.source_github, 1)
        source_top.addStretch()
        source_grid.addLayout(source_top, 0, 0, 1, 2)

        source_sep = QLabel("")
        source_sep.setFixedHeight(1)
        source_sep.setObjectName("subseparator")
        source_grid.addWidget(source_sep, 1, 0, 1, 2)

        self.local_source_label = QLabel("Local PDK")
        self.local_source_label.setObjectName("subtitle")
        self.local_source_input = QLineEdit()
        self.local_source_input.setPlaceholderText("Select local PDK directory")
        self.local_source_browse = QPushButton("Browse...")
        self.local_source_browse.setObjectName("browse_btn")
        self.local_source_browse.clicked.connect(self._on_local_source_browse)
        local_row = QHBoxLayout()
        local_row.addWidget(self.local_source_input, 1)
        local_row.addSpacing(8)
        local_row.addWidget(self.local_source_browse)
        source_grid.addWidget(self.local_source_label, 2, 0)
        source_grid.addLayout(local_row, 2, 1)

        self.github_mode_group = QButtonGroup(self)
        self.github_branch_radio = QRadioButton("Branch")
        self.github_commit_radio = QRadioButton("Specific Commit Hash")
        self.github_branch_radio.setChecked(True)
        self.github_mode_group.addButton(self.github_branch_radio, 0)
        self.github_mode_group.addButton(self.github_commit_radio, 1)
        gh_mode_row = QHBoxLayout()
        gh_mode_row.setSpacing(24)
        gh_mode_row.addWidget(self.github_branch_radio, 1)
        gh_mode_row.addWidget(self.github_commit_radio, 1)
        gh_mode_row.addStretch()
        self.github_mode_label = QLabel("GitHub Ref")
        self.github_mode_label.setObjectName("subtitle")
        source_grid.addWidget(self.github_mode_label, 3, 0)
        source_grid.addLayout(gh_mode_row, 3, 1)

        self.github_branch_label = QLabel("Branch")
        self.github_branch_label.setObjectName("subtitle")
        self.github_branch_combo = QComboBox()
        source_grid.addWidget(self.github_branch_label, 4, 0)
        source_grid.addWidget(self.github_branch_combo, 4, 1)

        self.github_commit_label = QLabel("Commit Hash")
        self.github_commit_label.setObjectName("subtitle")
        self.github_commit_input = QLineEdit()
        self.github_commit_input.setPlaceholderText("Leave empty to use default branch head")
        source_grid.addWidget(self.github_commit_label, 5, 0)
        source_grid.addWidget(self.github_commit_input, 5, 1)

        self.source_status = QLabel("")
        self.source_status.setWordWrap(True)
        self.source_status.hide()
        source_grid.addWidget(self.source_status, 6, 0, 1, 2)

        self.fetch_sg13g2_cb = QCheckBox("Get SG13G2 from GitHub")
        self.fetch_sg13g2_cb.hide()
        self.fetch_sg13g2_cb.stateChanged.connect(lambda *_: self.config_changed.emit())
        source_grid.addWidget(self.fetch_sg13g2_cb, 7, 0, 1, 2)

        mode_group = QGroupBox("Mode")
        mode_lay = QHBoxLayout()
        mode_lay.setSpacing(24)
        self.mode_btn_group = QButtonGroup(self)
        self.mode_new = QRadioButton("Install")
        self.mode_new.setChecked(True)
        self.mode_change = QRadioButton("Change PDK")
        self.mode_btn_group.addButton(self.mode_new, 0)
        self.mode_btn_group.addButton(self.mode_change, 1)
        mode_lay.addWidget(self.mode_new, 1)
        mode_lay.addWidget(self.mode_change, 1)
        mode_group.setLayout(mode_lay)
        grid.addWidget(mode_group, row, 1)
        row += 1

        source_group.setLayout(source_grid)
        grid.addWidget(source_group, row, 0, 1, 2)
        row += 1

        ic_group = QGroupBox("Install Config")
        ic_lay = QHBoxLayout()
        self.compile_va_cb = QCheckBox("Compile Verilog-A")
        self.compile_va_cb.setChecked(True)
        self.mode_btn_group.buttonClicked.connect(self._on_mode_changed)
        self.override_sg13g2_cb = QCheckBox("Override existing SG13G2")
        self.override_sg13g2_cb.hide()
        self.override_sg13g2_cb.setEnabled(False)
        self.override_sg13g2_cb.stateChanged.connect(lambda *_: self.config_changed.emit())
        ic_lay.addWidget(self.compile_va_cb)
        ic_lay.addWidget(self.override_sg13g2_cb)
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

        eda_group = QGroupBox("EDA Config")
        eda_grid = QGridLayout()
        eda_grid.setSpacing(8)

        self.sim_checks = {}
        self.sch_checks = {}
        self.lay_checks = {}
        self._eda_grid = eda_grid
        self._eda_all_items = []

        for sim in Simulator:
            if sim == Simulator.GNUCAP:
                continue
            tool = get_tool_definition(sim.value)
            cb = QCheckBox(tool.display_name)
            cb.setChecked(sim == Simulator.NGSPICE)
            cb.setProperty("sim_value", sim)
            self.sim_checks[sim] = cb
            self._eda_all_items.append((tool.id, "sim", sim, cb))

        for ed in SchematicEditor:
            tool = get_tool_definition(ed.value)
            cb = QCheckBox(tool.display_name)
            cb.setChecked(ed == SchematicEditor.XSCHEM)
            cb.setProperty("sch_value", ed)
            self.sch_checks[ed] = cb
            self._eda_all_items.append((tool.id, "sch", ed, cb))

        for ed in LayoutEditor:
            if ed == LayoutEditor.MAGIC:
                continue
            tool = get_tool_definition(ed.value)
            cb = QCheckBox(tool.display_name)
            cb.setChecked(ed == LayoutEditor.KLAYOUT)
            cb.setProperty("lay_value", ed)
            self.lay_checks[ed] = cb
            self._eda_all_items.append((tool.id, "lay", ed, cb))

        self._refresh_eda_visibility()

        eda_group.setLayout(eda_grid)
        grid.addWidget(eda_group, row, 0, 1, 2)
        row += 1

        root.addLayout(grid)
        root.addStretch()

        self.source_btn_group.buttonClicked.connect(self._on_source_type_changed)
        self.github_mode_group.buttonClicked.connect(self._on_github_mode_changed)
        self.github_branch_combo.currentIndexChanged.connect(lambda *_: self.config_changed.emit())
        self.github_commit_input.textChanged.connect(lambda *_: self.config_changed.emit())
        self.local_source_input.textChanged.connect(lambda *_: self.config_changed.emit())
        self.dir_input.textChanged.connect(lambda *_: self.config_changed.emit())
        self._update_github_branch_choices()
        self._update_source_visibility()

    def set_base_dir(self, base_dir: str):
        self._base_dir = base_dir
        self._update_dir_for_pdk()

    def _get_selected_pdk(self) -> str:
        for btn in self.pdk_btn_group.buttons():
            if btn.isChecked():
                return btn.property("pdk_value")
        return "ihp-sg13g2"

    def _on_pdk_changed(self, btn):
        self._update_github_branch_choices()
        self._refresh_eda_visibility()
        if self.source_local.isChecked():
            self._set_default_source_root_for_mode(force=True)
        self._update_dir_for_pdk()
        self.config_changed.emit()

    def _on_mode_changed(self, btn):
        self.compile_va_cb.setChecked(self.mode_new.isChecked())
        self._set_default_source_root_for_mode()
        self.config_changed.emit()

    def _on_source_type_changed(self, btn):
        self._update_source_visibility()
        self.config_changed.emit()

    def _on_github_mode_changed(self, btn):
        self._update_source_visibility()
        self.config_changed.emit()

    def _script_install_root(self) -> str:
        return self._script_root

    def _default_local_source_root(self) -> str:
        pdk_dir = self.PDK_DIR_MAP[self._get_selected_pdk()]
        if self.mode_change.isChecked():
            base = os.environ.get("PDK_ROOT") or self._script_install_root()
        else:
            base = self._script_install_root()
        return str(Path(base) / pdk_dir)

    def _set_default_source_root_for_mode(self, force: bool = False):
        if force or not self.local_source_input.text().strip() or self.source_local.isChecked():
            self.local_source_input.setText(self._default_local_source_root())
        self.source_local.setChecked(True)
        self._update_source_visibility()

    def _available_github_branches(self) -> list[str]:
        pdk = get_pdk_definition(self._get_selected_pdk())
        return list(pdk.allowed_branches)

    def _update_github_branch_choices(self):
        pdk_def = get_pdk_definition(self._get_selected_pdk())
        desired = self.github_branch_combo.currentText() or pdk_def.default_branch
        branches = self._available_github_branches()
        fallback = pdk_def.default_branch
        self.github_branch_combo.blockSignals(True)
        self.github_branch_combo.clear()
        self.github_branch_combo.addItems(branches)
        self.github_branch_combo.setCurrentText(desired if desired in branches else fallback)
        self.github_branch_combo.blockSignals(False)

    def _refresh_eda_visibility(self):
        supported = set(get_pdk_definition(self._get_selected_pdk()).supported_tools)
        visible = []
        for tool_id, _group, _item, cb in self._eda_all_items:
            is_supported = tool_id in supported
            cb.setVisible(is_supported)
            if not is_supported:
                cb.setChecked(False)
            else:
                visible.append(cb)

        cols = 3
        for index, cb in enumerate(visible):
            row, col = divmod(index, cols)
            self._eda_grid.addWidget(cb, row, col)

    def _update_source_visibility(self):
        is_local = self.source_local.isChecked()
        use_branch = self.github_branch_radio.isChecked()
        self.local_source_label.setVisible(is_local)
        self.local_source_input.setVisible(is_local)
        self.local_source_browse.setVisible(is_local)
        self.github_mode_label.setVisible(not is_local)
        self.github_branch_radio.setVisible(not is_local)
        self.github_commit_radio.setVisible(not is_local)
        self.github_branch_label.setVisible((not is_local) and use_branch)
        self.github_branch_combo.setVisible((not is_local) and use_branch)
        self.github_commit_label.setVisible(not is_local)
        self.github_commit_input.setVisible(not is_local)

    def _on_local_source_browse(self):
        start = self.local_source_input.text().strip()
        d = QFileDialog.getExistingDirectory(self, "Select Local PDK Directory", start)
        if d:
            self.local_source_input.setText(d)

    def set_source_status(self, ok: bool, message: str = ""):
        if ok or not message:
            self.source_status.hide()
            self.source_status.setText("")
            self.source_status.setObjectName("")
        else:
            self.source_status.setObjectName("result_warn")
            self.source_status.setText(message)
            self.source_status.show()
        self.source_status.setStyle(self.source_status.style())

    def set_source_pending_status(self, message: str):
        self.source_status.setObjectName("")
        self.source_status.setText(message)
        self.source_status.show()
        self.source_status.setStyle(self.source_status.style())

    def set_dependency_state(self, show_fetch: bool, target_valid: bool):
        is_cmos5l = self._get_selected_pdk() == PDKChoice.SG13CMOS5L.value
        self.fetch_sg13g2_cb.setVisible(is_cmos5l and show_fetch)
        self.override_sg13g2_cb.setVisible(is_cmos5l)
        self.override_sg13g2_cb.setEnabled(is_cmos5l and target_valid)
        if not show_fetch and self.fetch_sg13g2_cb.isChecked():
            self.fetch_sg13g2_cb.blockSignals(True)
            self.fetch_sg13g2_cb.setChecked(False)
            self.fetch_sg13g2_cb.blockSignals(False)
        if not target_valid and self.override_sg13g2_cb.isChecked():
            self.override_sg13g2_cb.blockSignals(True)
            self.override_sg13g2_cb.setChecked(False)
            self.override_sg13g2_cb.blockSignals(False)

    def _update_dir_for_pdk(self):
        if not self._base_dir:
            return
        pdk = self._get_selected_pdk()
        subdir = self.PDK_DIR_MAP.get(pdk, pdk)
        self.dir_input.setText(os.path.join(self._base_dir, subdir))

    def _on_browse(self):
        start = self.dir_input.text().strip()
        d = QFileDialog.getExistingDirectory(self, "Select Installation Directory", start)
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
        self.config.pdk_source_type = (
            PDKSourceType.LOCAL if self.source_local.isChecked() else PDKSourceType.GITHUB
        )
        self.config.local_source_root = self.local_source_input.text().strip() or None
        self.config.github_source_mode = (
            GitHubSourceMode.BRANCH if self.github_branch_radio.isChecked() else GitHubSourceMode.COMMIT
        )
        self.config.github_branch = self.github_branch_combo.currentText() or None
        self.config.github_commit = self.github_commit_input.text().strip() or None
        self.config.fetch_dependencies_from_github = self.fetch_sg13g2_cb.isChecked()
        self.config.override_existing_sg13g2 = self.override_sg13g2_cb.isChecked()

        self.config.install_dir = (
            self.dir_input.text().strip() or None
        )

        self.config.compile_verilog_a = self.compile_va_cb.isChecked()

        return self.config
