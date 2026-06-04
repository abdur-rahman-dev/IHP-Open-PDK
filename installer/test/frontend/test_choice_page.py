from installer.backend.models import GitHubSourceMode, InstallMode, LayoutEditor, PDKChoice, PDKSourceType, SchematicEditor, Simulator
from installer.frontend.choice_page import ChoicePage


def _make_page(qtbot, install_config):
    page = ChoicePage(install_config)
    qtbot.addWidget(page)
    page.show()
    return page


def test_default_selections(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    assert page._get_selected_pdk() == "ihp-sg13g2"
    assert page.mode_new.isChecked() is True
    assert page.compile_va_cb.isChecked() is True
    assert page.skip_tool_check_cb.isChecked() is False
    assert page.source_local.isChecked() is True
    assert page.github_branch_radio.isChecked() is True
    assert page.github_branch_combo.currentText() == "dev"
    assert page.sim_checks[Simulator.NGSPICE].isChecked() is True
    assert page.sch_checks[SchematicEditor.XSCHEM].isChecked() is True
    assert page.lay_checks[LayoutEditor.KLAYOUT].isChecked() is True


def test_set_base_dir_updates_sg13g2_suffix(qtbot, install_config, tmp_path):
    page = _make_page(qtbot, install_config)

    page.set_base_dir(str(tmp_path))

    assert page.dir_input.text() == str(tmp_path / "ihp-sg13g2")


def test_switching_pdk_updates_cmos5l_suffix(qtbot, install_config, tmp_path):
    page = _make_page(qtbot, install_config)
    page.set_base_dir(str(tmp_path))

    for btn in page.pdk_btn_group.buttons():
        if btn.property("pdk_value") == "ihp-sg13cmos5l":
            btn.click()
            break

    assert page.dir_input.text() == str(tmp_path / "ihp-sg13cmos5l")
    assert [page.github_branch_combo.itemText(i) for i in range(page.github_branch_combo.count())] == ["main"]


def test_install_mode_defaults_local_source_to_script_root(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    assert page.local_source_input.text() == f"{page._script_install_root()}/ihp-sg13g2"


def test_change_mode_unchecks_compile_va(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    page.mode_change.click()

    assert page.compile_va_cb.isChecked() is False
    assert page.source_local.isChecked() is True
    assert page.local_source_input.text().endswith("/ihp-sg13g2")


def test_install_mode_rechecks_compile_va(qtbot, install_config):
    page = _make_page(qtbot, install_config)
    page.mode_change.click()

    page.mode_new.click()

    assert page.compile_va_cb.isChecked() is True


def test_skip_tool_check_emits_signal(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    with qtbot.waitSignal(page.skip_tool_check_changed, timeout=1000) as blocker:
        page.skip_tool_check_cb.click()

    assert blocker.args == [True]


def test_switch_to_github_shows_github_controls(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    page.source_github.click()

    assert page.github_branch_radio.isVisible() is True
    assert page.github_commit_input.isVisible() is True
    assert page.local_source_input.isVisible() is False


def test_switch_to_commit_mode_keeps_commit_input_visible(qtbot, install_config):
    page = _make_page(qtbot, install_config)
    page.source_github.click()
    page.github_commit_radio.click()

    assert page.github_commit_input.isVisible() is True


def test_magic_is_not_visible_layout_choice(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    assert LayoutEditor.MAGIC not in page.lay_checks


def test_eda_choices_are_driven_by_supported_tools(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    assert page.sim_checks[Simulator.NGSPICE].isVisible() is True
    assert page.sim_checks[Simulator.XYCE].isVisible() is True
    assert page.sim_checks[Simulator.GNUCAP].isVisible() is True
    assert page.sch_checks[SchematicEditor.XSCHEM].isVisible() is True
    assert page.lay_checks[LayoutEditor.KLAYOUT].isVisible() is True


def test_get_config_serializes_current_ui_state(qtbot, install_config, tmp_path):
    page = _make_page(qtbot, install_config)
    page.set_base_dir(str(tmp_path))
    page.mode_change.click()
    page.skip_tool_check_cb.click()

    page.sim_checks[Simulator.NGSPICE].setChecked(False)
    page.sim_checks[Simulator.XYCE].setChecked(True)
    page.sch_checks[SchematicEditor.XSCHEM].setChecked(False)
    page.sch_checks[SchematicEditor.QUCS_S].setChecked(True)

    cfg = page.get_config()

    assert cfg.pdk == PDKChoice.SG13G2
    assert cfg.install_mode == InstallMode.CHANGE
    assert cfg.pdk_source_type == PDKSourceType.LOCAL
    assert cfg.github_source_mode == GitHubSourceMode.BRANCH
    assert cfg.skip_tool_check is True
    assert cfg.compile_verilog_a is False
    assert cfg.install_dir == str(tmp_path / "ihp-sg13g2")
    assert cfg.local_source_root == page.local_source_input.text()
    assert cfg.simulators == [Simulator.XYCE]
    assert cfg.schematic_editors == [SchematicEditor.QUCS_S]
    assert cfg.layout_editors == [LayoutEditor.KLAYOUT]


def test_switching_pdk_updates_default_local_source_dir(qtbot, install_config):
    page = _make_page(qtbot, install_config)

    for btn in page.pdk_btn_group.buttons():
        if btn.property("pdk_value") == "ihp-sg13cmos5l":
            btn.click()
            break

    assert page.local_source_input.text().endswith("/ihp-sg13cmos5l")


def test_get_config_serializes_github_source_fields(qtbot, install_config):
    page = _make_page(qtbot, install_config)
    page.source_github.click()
    page.github_commit_radio.click()
    page.github_commit_input.setText("deadbeef")

    cfg = page.get_config()

    assert cfg.pdk_source_type == PDKSourceType.GITHUB
    assert cfg.github_source_mode == GitHubSourceMode.COMMIT
    assert cfg.github_commit == "deadbeef"
    assert cfg.github_branch == "dev"
