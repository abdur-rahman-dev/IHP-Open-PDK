from dataclasses import dataclass


@dataclass(frozen=True)
class ToolDefinition:
    id: str
    display_name: str
    type: str
    show_in_tool_check: bool = True


TOOL_DEFINITIONS: tuple[ToolDefinition, ...] = (
    ToolDefinition("openvaf/openvaf-r", "openvaf", "compiler"),
    ToolDefinition("python3", "python3", "utility"),
    ToolDefinition("pip", "pip", "utility"),
    ToolDefinition("ngspice", "ngspice", "simulator"),
    ToolDefinition("Xyce", "Xyce", "simulator"),
    ToolDefinition("gnucap", "gnucap", "simulator"),
    ToolDefinition("xschem", "xschem", "schematic_editor"),
    ToolDefinition("qucs-s", "qucs-s", "schematic_editor"),
    ToolDefinition("klayout", "klayout", "layout_editor"),
    ToolDefinition("magic", "magic", "layout_editor"),
    ToolDefinition("netgen", "netgen", "utility"),
    ToolDefinition("openEMS", "openEMS", "utility"),
)


TOOL_DEFINITION_MAP = {tool.id: tool for tool in TOOL_DEFINITIONS}


def get_tool_definition(tool_id: str) -> ToolDefinition:
    return TOOL_DEFINITION_MAP[tool_id]


def get_tools_by_type(tool_type: str) -> list[ToolDefinition]:
    return [tool for tool in TOOL_DEFINITIONS if tool.type == tool_type]


def get_tool_check_tool_ids() -> list[str]:
    return [tool.id for tool in TOOL_DEFINITIONS if tool.show_in_tool_check]
