import os
import re
import subprocess
import hashlib
from pathlib import Path
from typing import Optional

from .models import (
    ToolInfo,
    ToolStatusEnum,
    EnvCheckResult,
    InstallConfig,
    InstallPlan,
    Simulator,
    SchematicEditor,
    LayoutEditor,
)

VERSION_FLAGS = {
    "ngspice": ["-v"],
    "klayout": ["-v"],
    "xschem": ["-v"],
    "qucs-s": ["-v"],
    "magic": ["--version"],
    "Xyce": ["-v"],
    "gnucap": ["-v"],
    "python3": ["--version"],
    "openvaf": ["--version"],
    "openvaf-r": ["--version"],
    "pip": ["--version"],
    "netgen": ["-noconsole quit"],
    "openEMS": ["-h"],
}

SAFE_VERSION_TOOLS = set(VERSION_FLAGS.keys())

MIN_KLAYOUT_VERSION = "0.29.0"
MIN_PYTHON_VERSION = "3.9"

OSDI_MODELS = [
    {"name": "psp103", "src_dir": "psp103", "va_file": "psp103.va"},
    {"name": "psp103_nqs", "src_dir": "psp103", "va_file": "psp103_nqs.va"},
    {"name": "r3_cmc", "src_dir": "r3_cmc", "va_file": "r3_cmc.va"},
    {"name": "mosvar", "src_dir": "mosvar", "va_file": "mosvar.va"},
]

XYCE_MODELS = [
    {"name": "psp103", "src_dir": "psp103", "va_file": "psp103.va"},
    {"name": "r3_cmc", "src_dir": "r3_cmc", "va_file": "r3_cmc.va"},
    {"name": "mosvar", "src_dir": "mosvar", "va_file": "mosvar.va"},
]


def is_program_installed(program: str) -> bool:
    try:
        subprocess.run(
            ["which", program],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
            timeout=5,
            start_new_session=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def get_version(program: str) -> Optional[str]:
    if program not in SAFE_VERSION_TOOLS:
        return None
    flags = VERSION_FLAGS.get(program, ["--version", "-V"])
    for flag in flags:
        try:
            result = subprocess.run(
                [program] + flag.split(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                timeout=10,
                start_new_session=True,
            )
            output = (result.stdout + result.stderr).strip()
            if not output:
                continue
            match = re.search(r"(v?\d+\.\d+[\.\d]*[\w\-]*)", output)
            if match:
                return match.group(1)
            match = re.search(r"[a-zA-Z][\w]*-?(\d+)", output)
            if match:
                return match.group(1)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass
    return None


def parse_version(version_str: str):
    parts = re.findall(r"\d+", version_str)
    return tuple(int(p) for p in parts) if parts else (0,)


def version_gte(installed: str, minimum: str) -> bool:
    return parse_version(installed) >= parse_version(minimum)


def md5_file(filepath: str) -> str:
    h = hashlib.md5()
    with open(filepath, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_tools(config: InstallConfig) -> list[ToolInfo]:
    results = []

    openvaf_name = None
    for prog in ["openvaf-r", "openvaf"]:
        if is_program_installed(prog):
            openvaf_name = prog
            break

    if openvaf_name:
        ver = get_version(openvaf_name)
        results.append(ToolInfo(
            name=openvaf_name, installed=True, version=ver,
            status=ToolStatusEnum.OK, required=True, category="compiler",
            message="Required for Verilog-A model compilation",
        ))
    else:
        results.append(ToolInfo(
            name="openvaf/openvaf-r", installed=False,
            status=ToolStatusEnum.ERROR, required=True, category="compiler",
            message="NOT FOUND - Required for model compilation",
        ))

    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    if version_gte(py_ver, MIN_PYTHON_VERSION):
        results.append(ToolInfo(
            name="python3", installed=True, version=py_ver,
            min_version=MIN_PYTHON_VERSION, status=ToolStatusEnum.OK,
            required=False, category="runtime",
        ))
    else:
        results.append(ToolInfo(
            name="python3", installed=True, version=py_ver,
            min_version=MIN_PYTHON_VERSION, status=ToolStatusEnum.WARNING,
            required=False, category="runtime",
            message=f"Version {py_ver} < minimum {MIN_PYTHON_VERSION}",
        ))

    sim_tools = []
    for sim in config.simulators:
        if sim == Simulator.NGSPICE:
            sim_tools.append(("ngspice", False, None))
        elif sim == Simulator.XYCE:
            sim_tools.append(("Xyce", False, None))
            sim_tools.append(("buildxyceplugin", False, None))
        elif sim == Simulator.GNUCAP:
            sim_tools.append(("gnucap", False, None))
            sim_tools.append(("gnucap-mg-vams", False, None))

    for tool_name, required, min_ver in sim_tools:
        if is_program_installed(tool_name):
            ver = get_version(tool_name)
            status = ToolStatusEnum.OK
            msg = ""
            if min_ver and ver and not version_gte(ver, min_ver):
                status = ToolStatusEnum.WARNING
                msg = f"Version {ver} < minimum {min_ver}"
            results.append(ToolInfo(
                name=tool_name, installed=True, version=ver,
                min_version=min_ver, status=status, required=required,
                category="simulator", message=msg,
            ))
        else:
            results.append(ToolInfo(
                name=tool_name, installed=False,
                min_version=min_ver, status=ToolStatusEnum.WARNING,
                required=False, category="simulator",
                message="Not found (optional)",
            ))

    editor_tools = []
    for ed in config.schematic_editors:
        if ed == SchematicEditor.XSCHEM:
            editor_tools.append(("xschem", None))
        elif ed == SchematicEditor.QUCS_S:
            editor_tools.append(("qucs-s", None))

    for ed in config.layout_editors:
        if ed == LayoutEditor.KLAYOUT:
            editor_tools.append(("klayout", MIN_KLAYOUT_VERSION))
        elif ed == LayoutEditor.MAGIC:
            editor_tools.append(("magic", None))

    for tool_name, min_ver in editor_tools:
        if is_program_installed(tool_name):
            ver = get_version(tool_name)
            status = ToolStatusEnum.OK
            msg = ""
            if min_ver and ver and not version_gte(ver, min_ver):
                status = ToolStatusEnum.WARNING
                msg = f"Version {ver} < minimum {min_ver}"
            results.append(ToolInfo(
                name=tool_name, installed=True, version=ver,
                min_version=min_ver, status=status, required=False,
                category="editor", message=msg,
            ))
        else:
            results.append(ToolInfo(
                name=tool_name, installed=False,
                min_version=min_ver, status=ToolStatusEnum.WARNING,
                required=False, category="editor",
                message="Not found",
            ))

    if is_program_installed("pip"):
        results.append(ToolInfo(
            name="pip", installed=True, version=get_version("pip"),
            status=ToolStatusEnum.OK, required=False, category="runtime",
        ))
    else:
        results.append(ToolInfo(
            name="pip", installed=False, status=ToolStatusEnum.WARNING,
            required=False, category="runtime", message="Not found",
        ))

    return results


def check_environment(config: InstallConfig) -> list[EnvCheckResult]:
    results = []
    pdk_root = config.get_target_pdk_root()
    home = os.environ.get("HOME", "")

    pdk_root_env = os.environ.get("PDK_ROOT")
    results.append(EnvCheckResult(
        variable="PDK_ROOT",
        is_set=pdk_root_env is not None,
        current_value=pdk_root_env,
        expected_value=pdk_root,
        action="Already set" if pdk_root_env == pdk_root else "Will set in .bashrc",
    ))

    pdk_env = os.environ.get("PDK")
    results.append(EnvCheckResult(
        variable="PDK",
        is_set=pdk_env is not None,
        current_value=pdk_env,
        expected_value=config.pdk.value,
        action="Already set" if pdk_env == config.pdk.value else "Will set in .bashrc",
    ))

    if LayoutEditor.KLAYOUT in config.layout_editors:
        klayout_path = os.environ.get("KLAYOUT_PATH", "")
        pdk_klayout = f"{pdk_root}/{config.pdk.value}/libs.tech/klayout"
        has_pdk = pdk_klayout in klayout_path
        results.append(EnvCheckResult(
            variable="KLAYOUT_PATH",
            is_set=has_pdk,
            current_value=klayout_path or None,
            expected_value=f"$HOME/.klayout:{pdk_klayout}",
            action="Already set" if has_pdk else "Will append to .bashrc",
        ))

        klayout_home = os.environ.get("KLAYOUT_HOME")
        results.append(EnvCheckResult(
            variable="KLAYOUT_HOME",
            is_set=klayout_home is not None,
            current_value=klayout_home,
            expected_value="$HOME/.klayout",
            action="Already set" if klayout_home else "Will set in .bashrc",
        ))

    spiceinit_src = os.path.join(
        pdk_root, config.pdk.value, "libs.tech", "ngspice", ".spiceinit"
    )
    spiceinit_dst = os.path.join(home, ".spiceinit")
    if os.path.islink(spiceinit_dst):
        target = os.readlink(spiceinit_dst)
        if os.path.exists(target) and os.path.exists(spiceinit_src):
            try:
                same = os.path.samefile(target, spiceinit_src)
            except OSError:
                same = False
            results.append(EnvCheckResult(
                variable=".spiceinit",
                is_set=same,
                current_value=target,
                expected_value=spiceinit_src,
                action="Valid symlink" if same else "Stale symlink - will fix",
            ))
        else:
            results.append(EnvCheckResult(
                variable=".spiceinit", is_set=False,
                current_value=target, expected_value=spiceinit_src,
                action="Will create symlink",
            ))
    elif os.path.exists(spiceinit_dst):
        results.append(EnvCheckResult(
            variable=".spiceinit", is_set=False,
            current_value="(file exists)", expected_value=spiceinit_src,
            action="File exists but not a symlink",
        ))
    else:
        results.append(EnvCheckResult(
            variable=".spiceinit", is_set=False,
            current_value=None, expected_value=spiceinit_src,
            action="Will create symlink",
        ))

    return results


def _check_selected_tools(config: InstallConfig) -> list[ToolInfo]:
    all_tools = check_tools(config)
    selected = set(config.tools_to_check)
    filtered = []
    for t in all_tools:
        base = t.name.split("/")[0]
        if base in selected or t.name in selected:
            filtered.append(t)
    return filtered


def build_install_plan(config: InstallConfig) -> InstallPlan:
    plan = InstallPlan(config=config)
    plan.pdk_root = config.get_target_pdk_root()

    if config.tools_to_check:
        plan.tools = _check_selected_tools(config)
    elif config.install_mode.value == "new":
        plan.tools = check_tools(config)

    plan.env_checks = check_environment(config)

    openvaf_tool = next(
        (t for t in plan.tools if t.name in ("openvaf", "openvaf-r", "openvaf/openvaf-r")),
        None,
    )
    openvaf_available = openvaf_tool and openvaf_tool.installed

    if not openvaf_available and config.install_mode.value == "new":
        plan.errors.append("openvaf/openvaf-r not found - required for Verilog-A compilation")

    for t in plan.tools:
        if t.status == ToolStatusEnum.ERROR:
            if t.required:
                plan.errors.append(f"{t.name}: {t.message}")
        elif t.status == ToolStatusEnum.WARNING:
            plan.warnings.append(f"{t.name}: {t.message}")

    for e in plan.env_checks:
        if not e.is_set:
            plan.actions.append(f"Set {e.variable} in .bashrc")

    if openvaf_available:
        pdk_root = config.get_target_pdk_root()
        osdi_dir = os.path.join(
            pdk_root, config.pdk.value, "libs.tech", "ngspice", "osdi"
        )
        for model in OSDI_MODELS:
            osdi_path = os.path.join(osdi_dir, f"{model['name']}.osdi")
            if not os.path.exists(osdi_path):
                plan.actions.append(
                    f"Compile {model['name']}.va -> {model['name']}.osdi"
                )
            else:
                plan.actions.append(f"OSDI model {model['name']}.osdi: already exists (skip)")

    if Simulator.XYCE in config.simulators:
        xyce_tool = next((t for t in plan.tools if t.name == "Xyce"), None)
        bxp_tool = next((t for t in plan.tools if t.name == "buildxyceplugin"), None)
        if xyce_tool and xyce_tool.installed and bxp_tool and bxp_tool.installed:
            for model in XYCE_MODELS:
                plan.actions.append(f"Compile Xyce plugin: {model['name']}")

    if Simulator.GNUCAP in config.simulators:
        gnucap_tool = next((t for t in plan.tools if t.name == "gnucap"), None)
        mg_tool = next((t for t in plan.tools if t.name == "gnucap-mg-vams"), None)
        if gnucap_tool and gnucap_tool.installed and mg_tool and mg_tool.installed:
            for model in OSDI_MODELS:
                plan.actions.append(f"Compile gnucap plugin: {model['name']}")

    if SchematicEditor.XSCHEM in config.schematic_editors:
        xschem_tool = next((t for t in plan.tools if t.name == "xschem"), None)
        if xschem_tool and xschem_tool.installed:
            plan.actions.append("Configure Xschem (spiceinit symlink already covered)")

    if SchematicEditor.QUCS_S in config.schematic_editors:
        qucs_tool = next((t for t in plan.tools if t.name == "qucs-s"), None)
        if qucs_tool and qucs_tool.installed:
            plan.actions.append("Symlink Qucs-S user_lib to $HOME/.qucs/ and $HOME/QucsWorkspace/")
            plan.actions.append("Copy Qucs-S example schematics")
            plan.actions.append("Fix workspace paths in .sch files")
            plan.actions.append("Create PDK root symlink in Qucs workspace")

    if LayoutEditor.KLAYOUT in config.layout_editors:
        plan.actions.append("Ensure KLAYOUT_PATH and KLAYOUT_HOME are set")

    if LayoutEditor.MAGIC in config.layout_editors:
        plan.actions.append("Configure Magic layout editor")

    if config.install_dir:
        src_root = config.get_source_pdk_root()
        target_root = config.get_target_pdk_root()
        plan.actions.insert(0, f"Copy PDK from {src_root}/{config.pdk.value} to {config.get_target_pdk_dir()}")
        plan.actions.insert(1, f"Update PDK_ROOT to {target_root}")

    return plan
