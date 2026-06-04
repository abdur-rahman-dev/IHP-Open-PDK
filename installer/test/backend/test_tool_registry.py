from installer.backend.tool_registry import get_tool_check_tool_ids, get_tool_definition, get_tools_by_type


def test_tool_registry_groups_visible_eda_tools():
    sims = [tool.id for tool in get_tools_by_type("simulator")]
    assert sims == ["ngspice", "Xyce", "gnucap"]

    layouts = [tool.id for tool in get_tools_by_type("layout_editor")]
    assert "klayout" in layouts
    assert "magic" in layouts


def test_tool_check_ids_include_openvaf_default_candidates():
    ids = get_tool_check_tool_ids()
    assert "openvaf/openvaf-r" in ids
    assert "klayout" in ids


def test_tool_definition_display_name():
    tool = get_tool_definition("openvaf/openvaf-r")
    assert tool.display_name == "openvaf"
    assert tool.type == "compiler"
