from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PDKChoice(str, Enum):
    SG13G2 = "ihp-sg13g2"
    SG13CMOS5L = "ihp-sg13cmos5l"


class Simulator(str, Enum):
    NGSPICE = "ngspice"
    XYCE = "Xyce"
    GNUCAP = "gnucap"


class SchematicEditor(str, Enum):
    XSCHEM = "xschem"
    QUCS_S = "qucs-s"


class LayoutEditor(str, Enum):
    KLAYOUT = "klayout"
    MAGIC = "magic"


class InstallMode(str, Enum):
    NEW = "new"
    CHANGE = "change"


class ToolStatusEnum(str, Enum):
    OK = "OK"
    WARNING = "WARN"
    ERROR = "ERROR"
    MISSING = "MISSING"
    NOT_CHECKED = "---"


@dataclass
class ToolInfo:
    name: str
    installed: bool = False
    version: Optional[str] = None
    min_version: Optional[str] = None
    status: ToolStatusEnum = ToolStatusEnum.NOT_CHECKED
    required: bool = False
    category: str = ""
    message: str = ""


@dataclass
class EnvCheckResult:
    variable: str
    is_set: bool = False
    current_value: Optional[str] = None
    expected_value: Optional[str] = None
    action: str = ""


@dataclass
class InstallConfig:
    pdk: PDKChoice = PDKChoice.SG13G2
    simulators: list[Simulator] = field(default_factory=lambda: [Simulator.NGSPICE])
    schematic_editors: list[SchematicEditor] = field(
        default_factory=lambda: [SchematicEditor.XSCHEM]
    )
    layout_editors: list[LayoutEditor] = field(
        default_factory=lambda: [LayoutEditor.KLAYOUT]
    )
    install_mode: InstallMode = InstallMode.NEW
    install_dir: Optional[str] = None
    pdk_root: Optional[str] = None

    def get_pdk_root(self) -> str:
        if self.install_dir:
            return self.install_dir
        if self.pdk_root:
            return self.pdk_root
        import os
        from pathlib import Path
        env_val = os.environ.get("PDK_ROOT")
        if env_val:
            return env_val
        script_dir = Path(__file__).resolve().parent
        for candidate in [script_dir, script_dir.parent]:
            if candidate.name in ("installer", "ihp-sg13g2", "ihp-sg13cmos5l"):
                candidate = candidate.parent
            for child in candidate.iterdir():
                if child.is_dir() and (child / "libs.tech").is_dir():
                    return str(candidate)
        return str(script_dir.parent)


@dataclass
class InstallPlan:
    config: InstallConfig
    tools: list[ToolInfo] = field(default_factory=list)
    env_checks: list[EnvCheckResult] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    pdk_root: Optional[str] = None

    def has_errors(self) -> bool:
        return len(self.errors) > 0 or any(
            t.status == ToolStatusEnum.ERROR for t in self.tools
        )

    def has_warnings(self) -> bool:
        return len(self.warnings) > 0 or any(
            t.status == ToolStatusEnum.WARNING for t in self.tools
        )

    def to_markdown(self) -> str:
        import datetime
        lines = [
            f"# IHP-Open-PDK Installation Plan",
            f"",
            f"**Generated:** {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"",
            f"## Configuration",
            f"",
            f"| Setting | Value |",
            f"|---|---|",
            f"| PDK | `{self.config.pdk.value}` |",
            f"| Install Mode | {self.config.install_mode.value} |",
            f"| PDK_ROOT | `{self.config.get_pdk_root()}` |",
            f"| Simulators | {', '.join(s.value for s in self.config.simulators)} |",
            f"| Schematic Editors | {', '.join(e.value for e in self.config.schematic_editors)} |",
            f"| Layout Editors | {', '.join(e.value for e in self.config.layout_editors)} |",
        ]

        if self.config.install_dir:
            lines += [
                f"| Install Dir | `{self.config.install_dir}` |",
                f"",
                f"### Installation Directory",
                f"",
                f"PDK will be copied from `{self.config.pdk_root}` to `{self.config.install_dir}`.",
                f"PDK_ROOT will be updated to the new location.",
            ]

        lines += [
            f"",
            f"## Tool Check Results",
            f"",
            f"| Tool | Status | Version | Required | Notes |",
            f"|---|---|---|---|---|",
        ]
        for t in self.tools:
            req = "Yes" if t.required else "No"
            ver = t.version or "---"
            notes = t.message or ""
            lines.append(f"| `{t.name}` | {t.status.value} | {ver} | {req} | {notes} |")

        if self.env_checks:
            lines += [
                f"",
                f"## Environment Variables",
                f"",
                f"| Variable | Set | Current Value | Action |",
                f"|---|---|---|---|",
            ]
            for e in self.env_checks:
                set_str = "Yes" if e.is_set else "No"
                val = f"`{e.current_value}`" if e.current_value else "---"
                lines.append(f"| `{e.variable}` | {set_str} | {val} | {e.action} |")

        if self.actions:
            lines += ["", f"## Planned Actions", ""]
            for i, a in enumerate(self.actions, 1):
                lines.append(f"{i}. {a}")

        if self.warnings:
            lines += ["", f"## Warnings", ""]
            for w in self.warnings:
                lines.append(f"- {w}")

        if self.errors:
            lines += ["", f"## Errors", ""]
            for e in self.errors:
                lines.append(f"- {e}")

        result = "\n".join(lines)
        if not self.has_errors() and not self.has_warnings():
            lines += ["", f"**Result: SUCCESS**"]
        elif not self.has_errors():
            lines += ["", f"**Result: SUCCESS with warnings**"]
        else:
            lines += ["", f"**Result: FAILED**"]

        return "\n".join(lines)
