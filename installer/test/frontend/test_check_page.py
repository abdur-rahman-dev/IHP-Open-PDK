from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit

from installer.backend.models import EnvCheckResult, LayoutEditor, Simulator, ToolInfo, ToolStatusEnum
from installer.frontend.check_page import CheckPage, _canonical_tool_name, _tool_display_name


def _make_page(qtbot, install_config, theme_manager):
    page = CheckPage(install_config, theme_manager)
    qtbot.addWidget(page)
    page.show()
    return page


def test_all_tc_tools_visible_list(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)

    assert len(page.ALL_TC_TOOLS) == 11
    assert "openvaf/openvaf-r" not in page.ALL_TC_TOOLS
    assert "buildxyceplugin" not in page.ALL_TC_TOOLS
    assert "gnucap-mg-vams" not in page.ALL_TC_TOOLS


def test_openvaf_canonical_and_display_mapping():
    assert _canonical_tool_name("openvaf") == "openvaf"
    assert _canonical_tool_name("openvaf-r") == "openvaf"
    assert _canonical_tool_name("openvaf/openvaf-r") == "openvaf"
    assert _tool_display_name("openvaf-r") == "openvaf"
    assert _tool_display_name("ngspice") == "ngspice"


def test_configured_tools_auto_include_hidden_dependencies(qtbot, install_config, theme_manager):
    install_config.simulators = [Simulator.NGSPICE, Simulator.XYCE, Simulator.GNUCAP]
    page = _make_page(qtbot, install_config, theme_manager)

    tools = set(page._configured_tools())

    assert "ngspice" in tools
    assert "Xyce" in tools
    assert "gnucap" in tools
    assert "openvaf/openvaf-r" in tools
    assert "buildxyceplugin" in tools
    assert "gnucap-mg-vams" in tools


def test_sync_tc_from_eda_checks_only_visible_tools(qtbot, install_config, theme_manager):
    install_config.simulators = [Simulator.XYCE]
    page = _make_page(qtbot, install_config, theme_manager)

    page._sync_tc_from_eda()

    assert page.tc_checks["Xyce"].isChecked() is True
    assert page.tc_checks["python3"].isChecked() is False
    assert "buildxyceplugin" not in page.tc_checks


def test_show_tool_selection_emits_nav_state(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)

    with qtbot.waitSignal(page.nav_state_changed, timeout=1000) as blocker:
        page.show_tool_selection()

    assert page._tc_phase == "selection"
    assert page.tc_section.isVisible() is True
    assert page.hint_label.text() == "Select tools to check, then click Check."
    assert blocker.args[0]["next_text"] == "Check"


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

    assert page.env_table.columnCount() == 3
    assert page.env_table.item(0, 1).text() == "/tmp/pdk"
    assert page.env_table.item(0, 2).text() == "Already set"
    assert page.env_table.item(1, 1).text() == "---"
    assert page.env_table.item(1, 2).text() == "Will set in .bashrc → $HOME/.klayout"


def test_refresh_overall_status_updates_result_label(qtbot, install_config, theme_manager):
    page = _make_page(qtbot, install_config, theme_manager)
    page.plan = type("Plan", (), {})()
    page.plan.tools = [ToolInfo(name="python3", installed=True, status=ToolStatusEnum.OK)]
    page.config.simulators = []

    page._refresh_overall_status()

    assert page.result_label.text() == "All checked tools found"


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
