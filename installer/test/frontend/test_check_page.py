from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QMessageBox, QTableWidget

from installer.backend.models import (
    EnvCheckResult,
    InstallPlan,
    LayoutEditor,
    PDKSourceType,
    Simulator,
    ToolInfo,
    ToolStatusEnum,
)
from installer.frontend.check_page import CheckPage, _canonical_tool_name, _tool_display_name


def _make_page(qtbot, install_config, theme_manager):
    page = CheckPage(install_config, theme_manager)
    qtbot.addWidget(page)
    page.show()
    return page


def test_all_tc_tools_visible_list(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)

    assert len(page.ALL_TC_TOOLS) == 12
    assert "openvaf/openvaf-r" in page.ALL_TC_TOOLS
    assert "buildxyceplugin" not in page.ALL_TC_TOOLS
    assert "gnucap-mg-vams" not in page.ALL_TC_TOOLS
    assert page.tools_table.selectionMode() == QTableWidget.SelectionMode.NoSelection


def test_openvaf_canonical_and_display_mapping():
    assert _canonical_tool_name("openvaf") == "openvaf"
    assert _canonical_tool_name("openvaf-r") == "openvaf"
    assert _canonical_tool_name("openvaf/openvaf-r") == "openvaf"
    assert _tool_display_name("openvaf-r") == "openvaf"
    assert _tool_display_name("ngspice") == "ngspice"


def test_show_tool_selection_uses_tool_check_defaults_only(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)

    page.show_tool_selection()

    assert page.tc_checks["openvaf/openvaf-r"].isChecked() is True
    assert page.tc_checks["klayout"].isChecked() is True
    assert page.tc_checks["ngspice"].isChecked() is False


def test_show_tool_selection_emits_nav_state(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)

    with qtbot.waitSignal(page.nav_state_changed, timeout=1000) as blocker:
        page.show_tool_selection()

    assert page._tc_phase == "selection"
    assert page.tc_section.isVisible() is True
    assert page.hint_label.text() == "Select tools to check, then click Check."
    assert blocker.args[0]["next_text"] == "Check"
    assert blocker.args[0]["next_enabled"] is True


def test_show_tool_selection_without_defaults_preserves_existing_selection(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    page.show_tool_selection()
    page.tc_checks["openvaf/openvaf-r"].setChecked(False)
    page.tc_checks["python3"].setChecked(True)

    page.show_tool_selection(use_defaults=False)

    assert page.tc_checks["openvaf/openvaf-r"].isChecked() is False
    assert page.tc_checks["python3"].isChecked() is True


def test_tc_toggle_enables_next_when_any_selected(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    page.show_tool_selection()

    with qtbot.waitSignal(page.nav_state_changed, timeout=1000) as blocker:
        page.tc_checks["python3"].click()

    assert blocker.args[0]["next_enabled"] is True
    assert blocker.args[0]["next_text"] == "Check"


def test_load_recommended_versions_maps_python(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)

    assert page._recommended_versions["python3"] == "3.10.12"
    assert page._recommended_versions["klayout"] == "0.30.3"


def test_populate_tools_installed_row_shows_path_tooltip(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    tools = [
        ToolInfo(
            name="python3",
            installed=True,
            version="3.12.3",
            status=ToolStatusEnum.OK,
            install_path="/usr/bin/python3",
        )
    ]

    page._populate_tools(tools)

    item = page.tools_table.item(0, 4)
    assert item is not None
    assert item.text() == "/usr/bin/python3"
    assert item.toolTip() == "/usr/bin/python3"


def test_populate_tools_missing_row_has_path_widget(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    tools = [ToolInfo(name="ngspice", installed=False, status=ToolStatusEnum.WARNING)]

    page._populate_tools(tools)

    widget = page.tools_table.cellWidget(0, 4)
    assert widget is not None
    line_edit = widget.findChild(QLineEdit)
    assert line_edit is not None
    assert line_edit.placeholderText() == "Select executable..."


def test_populate_tools_klayout_python_row_uses_package_dir_widget(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    tools = [
        ToolInfo(name="klayout", installed=True, version="0.30.5", status=ToolStatusEnum.OK),
        ToolInfo(
            name="klayout-python",
            installed=True,
            version="0.30.8",
            status=ToolStatusEnum.WARNING,
            install_path="/tmp/site-packages/klayout/__init__.py",
        ),
    ]

    page._populate_tools(tools)

    widget = page.tools_table.cellWidget(1, 4)
    assert widget is not None
    line_edit = widget.findChild(QLineEdit)
    assert line_edit is not None
    assert line_edit.text() == "/tmp/site-packages/klayout"
    assert page.tools_table.item(1, 3).text() == "0.30.3"
    mismatch, message = page._check_klayout_python_mismatch("0.30.8")
    assert mismatch is True
    assert "Version mismatch" in message


def test_populate_env_uses_three_columns_and_formats_missing_values(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    env_checks = [
        EnvCheckResult(variable="PDK_ROOT", is_set=True, current_value="/tmp/pdk", action="Already set"),
        EnvCheckResult(variable="KLAYOUT_HOME", is_set=False, current_value=None, expected_value="$HOME/.klayout", action="Will set in .bashrc"),
    ]

    page._populate_env(env_checks)

    assert page.env_scroll.isVisible() is True
    texts = [label.text() for label in page.env_report_widget.findChildren(type(page.result_label))]
    assert "PDK_ROOT" in texts
    assert "Current value: /tmp/pdk" in texts
    assert "Action: Already set" in texts
    assert "KLAYOUT_HOME" in texts
    assert "Current value: ---" in texts
    assert "Action: Will set in .bashrc → $HOME/.klayout" in texts


def test_start_env_and_install_keeps_install_enabled_for_informational_env_state(qtbot, install_config, theme_manager, monkeypatch):
    page = _make_page(qtbot, install_config, theme_manager)
    page.plan = InstallPlan(config=install_config)
    emitted = []
    page.nav_state_changed.connect(emitted.append)
    monkeypatch.setattr("installer.frontend.check_page.check_environment", lambda cfg: [
        EnvCheckResult(variable="PDK_ROOT", is_set=False, current_value=None, expected_value="/tmp/pdk", action="Will set")
    ])

    page.start_env_and_install()

    assert emitted[-1]["next_enabled"] is True
    assert emitted[-1]["next_text"] == "Install"


def test_refresh_overall_status_updates_result_label(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    page.plan = InstallPlan(config=install_config)
    page.plan.tools = [ToolInfo(name="python3", installed=True, status=ToolStatusEnum.OK)]
    page.config.simulators = []
    page.config.compile_verilog_a = False

    page._refresh_overall_status()

    assert page.result_label.text() == "All checked tools found"


def test_confirm_install_if_needed_returns_true_without_override(qtbot, install_config, theme_manager, monkeypatch):
    page = _make_page(qtbot, install_config, theme_manager)
    page.plan = InstallPlan(config=install_config)
    seen = {"called": False}

    def fake_question(*args, **kwargs):
        seen["called"] = True
        return QMessageBox.StandardButton.Yes

    monkeypatch.setattr("installer.frontend.check_page.QMessageBox.question", fake_question)

    assert page.confirm_install_if_needed() is True
    assert seen["called"] is False


def test_confirm_install_if_needed_blocks_on_cancel(qtbot, install_config, theme_manager, monkeypatch):
    page = _make_page(qtbot, install_config, theme_manager)
    page.plan = InstallPlan(config=install_config)
    page.plan.env_checks = [
        EnvCheckResult(
            variable="Install Destination",
            current_value="/tmp/target/ihp-sg13g2",
            expected_value="/tmp/target/ihp-sg13g2",
            action="Destination will be overridden",
            requires_confirmation=True,
            reason_code="install_destination_override",
        )
    ]

    monkeypatch.setattr(
        "installer.frontend.check_page.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Cancel,
    )

    assert page.confirm_install_if_needed() is False


def test_confirm_install_if_needed_allows_on_confirm(qtbot, install_config, theme_manager, monkeypatch):
    page = _make_page(qtbot, install_config, theme_manager)
    page.config.pdk_source_type = PDKSourceType.GITHUB
    page.plan = InstallPlan(config=install_config)
    page.plan.env_checks = [
        EnvCheckResult(
            variable="Install Destination",
            current_value="/tmp/target/ihp-sg13g2",
            expected_value="/tmp/target/ihp-sg13g2",
            action="Destination will be overridden",
            requires_confirmation=True,
            reason_code="install_destination_override",
        )
    ]

    monkeypatch.setattr(
        "installer.frontend.check_page.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    assert page.confirm_install_if_needed() is True


def test_check_klayout_python_from_path_reads_metadata(qtbot, install_config, theme_manager, tmp_path):
    page = _make_page(qtbot, install_config, theme_manager)
    site = tmp_path / "site-packages"
    pkg = site / "klayout"
    dist = site / "klayout-0.30.8.dist-info"
    pkg.mkdir(parents=True)
    dist.mkdir(parents=True)
    (pkg / "__init__.py").write_text("# pkg\n")
    (dist / "METADATA").write_text("Name: klayout\nVersion: 0.30.8\n")

    version, valid = page._check_klayout_python_from_path(str(pkg))

    assert valid is True
    assert version == "0.30.8"


def test_dialog_start_dir_prefers_existing_directory(qtbot, install_config, theme_manager, tmp_path):
    page = _make_page(qtbot, install_config, theme_manager)

    assert page._dialog_start_dir(str(tmp_path)) == str(tmp_path)


def test_dialog_start_dir_uses_parent_for_existing_file(qtbot, install_config, theme_manager, tmp_path):
    page = _make_page(qtbot, install_config, theme_manager)
    exe = tmp_path / "bin" / "ngspice"
    exe.parent.mkdir(parents=True)
    exe.write_text("#!/bin/sh\n")

    assert page._dialog_start_dir(str(exe), expect_file=True) == str(exe.parent)


def test_missing_tool_browse_uses_current_field_directory(qtbot, install_config, theme_manager, tmp_path, monkeypatch):
    page = _make_page(qtbot, install_config, theme_manager)
    tool = ToolInfo(name="ngspice", installed=False, status=ToolStatusEnum.WARNING)
    page._populate_tools([tool])

    widget = page.tools_table.cellWidget(0, 4)
    line_edit = widget.findChild(QLineEdit)
    selected = tmp_path / "bin" / "ngspice"
    selected.parent.mkdir(parents=True)
    selected.write_text("#!/bin/sh\n")
    line_edit.setText(str(selected))

    seen = {}

    def fake_open_file_name(parent, title, directory):
        seen["directory"] = directory
        return str(selected), ""

    monkeypatch.setattr("installer.frontend.check_page.QFileDialog.getOpenFileName", fake_open_file_name)
    monkeypatch.setattr(page, "_check_custom_path_version", lambda path, name: "43")
    page.plan = InstallPlan(config=install_config)
    page.plan.tools = [tool]

    button = widget.findChildren(type(page.refresh_all_btn))[0]
    qtbot.mouseClick(button, Qt.LeftButton)

    assert seen["directory"] == str(selected.parent)


def test_klayout_python_browse_uses_current_field_directory(qtbot, install_config, theme_manager, tmp_path, monkeypatch):
    page = _make_page(qtbot, install_config, theme_manager)
    tools = [
        ToolInfo(name="klayout", installed=True, version="0.30.5", status=ToolStatusEnum.OK),
        ToolInfo(name="klayout-python", installed=False, status=ToolStatusEnum.WARNING),
    ]
    page._populate_tools(tools)

    widget = page.tools_table.cellWidget(1, 4)
    line_edit = widget.findChild(QLineEdit)
    pkg_dir = tmp_path / "site-packages" / "klayout"
    pkg_dir.mkdir(parents=True)
    line_edit.setText(str(pkg_dir))

    seen = {}

    def fake_get_existing_directory(parent, title, directory):
        seen["directory"] = directory
        return str(pkg_dir)

    monkeypatch.setattr("installer.frontend.check_page.QFileDialog.getExistingDirectory", fake_get_existing_directory)
    monkeypatch.setattr(page, "_check_klayout_python_from_path", lambda path: ("0.30.5", True))
    page.plan = InstallPlan(config=install_config)
    page.plan.tools = tools

    button = widget.findChildren(type(page.refresh_all_btn))[0]
    qtbot.mouseClick(button, Qt.LeftButton)

    assert seen["directory"] == str(pkg_dir)
