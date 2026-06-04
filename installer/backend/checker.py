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
    PDKChoice,
    PDKSourceType,
)

VERSION_FLAGS = {
    "ngspice": ["-v"],
    "klayout": ["-v"],
    "klayout-python": [],
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

GITHUB_REPOS = {
    PDKChoice.SG13G2: "https://github.com/IHP-GmbH/IHP-Open-PDK.git",
    PDKChoice.SG13CMOS5L: "https://github.com/IHP-GmbH/ihp-sg13cmos5l.git",
}


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


def get_which_path(program: str) -> Optional[str]:
    try:
        result = subprocess.run(
            ["which", program],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=True,
            timeout=5,
            start_new_session=True,
        )
        path = result.stdout.strip()
        return path if path else None
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def check_klayout_python() -> tuple[bool, Optional[str], Optional[str]]:
    try:
        import klayout
        pkg_path = getattr(klayout, "__file__", None)
        ver = None
        try:
            import importlib.metadata
            ver = importlib.metadata.version("klayout")
        except Exception:
            ver = getattr(klayout, "__version__", None)
        return True, ver, pkg_path
    except ImportError:
        return False, None, None


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


def get_github_repo_url(config: InstallConfig) -> str:
    return GITHUB_REPOS[config.pdk]


def validate_local_source(config: InstallConfig) -> tuple[bool, str]:
    pdk_dir = (config.local_source_root or "").strip()
    if not pdk_dir:
        return False, "Select a local PDK directory."
    norm = os.path.normpath(pdk_dir)
    expected = config.get_selected_pdk_dirname()
    if os.path.basename(norm) != expected:
        return False, (
            f"Selected folder '{norm}' is not the expected PDK directory '{expected}'.\n"
            f"Select the PDK directory itself, not the PDK root."
        )
    parent = os.path.dirname(norm)
    if not parent or parent == norm:
        return False, "Cannot derive PDK root from the selected folder. Select the PDK directory itself, not the PDK root."
    missing = []
    if not os.path.isdir(pdk_dir):
        missing.append(pdk_dir)
    libs_tech = os.path.join(pdk_dir, "libs.tech")
    libs_ref = os.path.join(pdk_dir, "libs.ref")
    if not os.path.isdir(libs_tech):
        missing.append(libs_tech)
    if not os.path.isdir(libs_ref):
        missing.append(libs_ref)
    if missing:
        return False, "Missing required paths:\n" + "\n".join(missing)
    return True, ""


def validate_github_source(config: InstallConfig) -> tuple[bool, str]:
    if not is_program_installed("git"):
        return False, "Git is not installed. Please use From Local."

    repo = get_github_repo_url(config)
    ref = config.get_effective_github_ref()
    try:
        result = subprocess.run(
            ["git", "ls-remote", repo],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=15,
            check=False,
            start_new_session=True,
        )
    except subprocess.TimeoutExpired:
        return False, "Timed out while contacting GitHub. Please use From Local."
    except OSError as exc:
        return False, f"Unable to run git: {exc}. Please use From Local."

    if result.returncode != 0:
        msg = (result.stderr or result.stdout).strip() or "GitHub source is unreachable."
        return False, f"{msg} Please use From Local."

    lines = [line.split()[0] for line in result.stdout.splitlines() if line.strip()]
    if config.github_source_mode.value == "branch":
        branch_ref = f"refs/heads/{ref}"
        if branch_ref not in result.stdout:
            return False, f"Branch '{ref}' is not available in the selected GitHub repository."
        return True, ""

    commit = (config.github_commit or "").strip()
    if not commit:
        fallback_ref = f"refs/heads/{ref}"
        if fallback_ref not in result.stdout:
            return False, f"Fallback branch '{ref}' is not available in the selected GitHub repository."
        return True, ""

    if any(sha.startswith(commit) for sha in lines):
        return True, ""
    return False, f"Commit '{commit}' was not found in the selected GitHub repository."


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
            install_path=get_which_path(openvaf_name),
        ))
    else:
        results.append(ToolInfo(
            name="openvaf/openvaf-r", installed=False,
            status=ToolStatusEnum.ERROR, required=True, category="compiler",
            message="NOT FOUND - Required for model compilation",
        ))

    import sys
    py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    py_path = get_which_path("python3") or sys.executable
    if version_gte(py_ver, MIN_PYTHON_VERSION):
        results.append(ToolInfo(
            name="python3", installed=True, version=py_ver,
            min_version=MIN_PYTHON_VERSION, status=ToolStatusEnum.OK,
            required=False, category="runtime", install_path=py_path,
        ))
    else:
        results.append(ToolInfo(
            name="python3", installed=True, version=py_ver,
            min_version=MIN_PYTHON_VERSION, status=ToolStatusEnum.WARNING,
            required=False, category="runtime",
            message=f"Version {py_ver} < minimum {MIN_PYTHON_VERSION}",
            install_path=py_path,
        ))

    sim_tools = []
    for sim in config.get_effective_simulators():
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
                install_path=get_which_path(tool_name),
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

    klayout_binary_ver = None
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
                install_path=get_which_path(tool_name),
            ))
            if tool_name == "klayout":
                klayout_binary_ver = ver
        else:
            results.append(ToolInfo(
                name=tool_name, installed=False,
                min_version=min_ver, status=ToolStatusEnum.WARNING,
                required=False, category="editor",
                message="Not found",
            ))

    has_klayout = LayoutEditor.KLAYOUT in config.layout_editors
    if has_klayout:
        py_installed, py_ver, py_path = check_klayout_python()
        if py_installed:
            msg = ""
            status = ToolStatusEnum.OK
            if klayout_binary_ver and py_ver:
                if parse_version(py_ver) != parse_version(klayout_binary_ver):
                    status = ToolStatusEnum.WARNING
                    msg = f"Version mismatch: binary {klayout_binary_ver} vs package {py_ver}"
            results.append(ToolInfo(
                name="klayout-python", installed=True, version=py_ver,
                status=status, required=False, category="editor",
                message=msg, install_path=py_path,
            ))
        else:
            results.append(ToolInfo(
                name="klayout-python", installed=False,
                status=ToolStatusEnum.WARNING, required=False, category="editor",
                message="Python package not found in current env",
            ))

    if is_program_installed("pip"):
        results.append(ToolInfo(
            name="pip", installed=True, version=get_version("pip"),
            status=ToolStatusEnum.OK, required=False, category="runtime",
            install_path=get_which_path("pip"),
        ))
    else:
        results.append(ToolInfo(
            name="pip", installed=False, status=ToolStatusEnum.WARNING,
            required=False, category="runtime", message="Not found",
        ))

    return results


def check_tools_for_names(tool_names: list[str], config: InstallConfig) -> list[ToolInfo]:
    cfg = InstallConfig(
        pdk=config.pdk,
        simulators=[],
        schematic_editors=[],
        layout_editors=[],
        install_mode=config.install_mode,
        install_dir=config.install_dir,
        pdk_root=config.pdk_root,
        pdk_source_type=config.pdk_source_type,
        local_source_root=config.local_source_root,
        github_source_mode=config.github_source_mode,
        github_branch=config.github_branch,
        github_commit=config.github_commit,
        compile_verilog_a=config.compile_verilog_a,
        skip_tool_check=config.skip_tool_check,
    )
    selected = {_canonical_tool_name_for_check(t) for t in tool_names}
    for sim in Simulator:
        if sim.value in selected:
            cfg.simulators.append(sim)
    for ed in SchematicEditor:
        if ed.value in selected:
            cfg.schematic_editors.append(ed)
    for ed in LayoutEditor:
        if ed.value in selected:
            cfg.layout_editors.append(ed)

    all_tools = check_tools(cfg)
    filtered = []
    include_klayout_python = "klayout" in selected
    for tool in all_tools:
        canonical = _canonical_tool_name_for_check(tool.name)
        if canonical in selected:
            filtered.append(tool)
        elif tool.name == "klayout-python" and include_klayout_python:
            filtered.append(tool)
    return filtered


def _canonical_tool_name_for_check(name: str) -> str:
    if name in ("openvaf", "openvaf-r", "openvaf/openvaf-r"):
        return "openvaf"
    return name


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

    if config.install_mode.value == "new" and config.install_dir:
        source_kind = "GitHub source" if config.pdk_source_type == PDKSourceType.GITHUB else "local source"
        source_root = config.get_source_pdk_root()
        target_root = config.get_target_pdk_root()
        target_pdk_dir = config.get_target_pdk_dir()
        will_sync = config.pdk_source_type == PDKSourceType.GITHUB or target_root != source_root

        if will_sync:
            if not os.path.exists(target_pdk_dir):
                action = f"Will populate destination from {source_kind}"
                current_value = target_pdk_dir
            elif os.path.isdir(target_pdk_dir) and not os.listdir(target_pdk_dir):
                action = f"Will populate empty destination from {source_kind}"
                current_value = target_pdk_dir
            else:
                action = f"Destination will be overridden with new contents from {source_kind}"
                current_value = target_pdk_dir
        else:
            action = "Using current location"
            current_value = target_pdk_dir

        results.append(EnvCheckResult(
            variable="Install Destination",
            is_set=not will_sync,
            current_value=current_value,
            expected_value=target_pdk_dir,
            action=action,
        ))

    return results


def _check_selected_tools(config: InstallConfig) -> list[ToolInfo]:
    all_tools = check_tools(config)
    selected = set(config.tools_to_check)
    filtered = []
    has_klayout = False
    for t in all_tools:
        base = t.name.split("/")[0]
        if base in selected or t.name in selected:
            filtered.append(t)
            if t.name == "klayout":
                has_klayout = True
        elif t.name == "klayout-python" and has_klayout:
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

    if config.compile_verilog_a and not openvaf_available and config.install_mode.value == "new":
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

    if Simulator.XYCE in config.get_effective_simulators():
        xyce_tool = next((t for t in plan.tools if t.name == "Xyce"), None)
        bxp_tool = next((t for t in plan.tools if t.name == "buildxyceplugin"), None)
        if xyce_tool and xyce_tool.installed and bxp_tool and bxp_tool.installed:
            for model in XYCE_MODELS:
                plan.actions.append(f"Compile Xyce plugin: {model['name']}")

    if Simulator.GNUCAP in config.get_effective_simulators():
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
