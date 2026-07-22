import sys
from argparse import Namespace

from .checker import build_install_plan, validate_source_with_dependencies
from .executor import InstallExecutor
from .models import (
    EnvCheckResult,
    ExecStepStatus,
    GitHubSourceMode,
    InstallConfig,
    InstallMode,
    LayoutEditor,
    PDKChoice,
    PDKSourceType,
    SchematicEditor,
    Simulator,
)


EDA_CONFIG_MAP = {
    "ngspice": ("simulators", Simulator.NGSPICE),
    "xyce": ("simulators", Simulator.XYCE),
    "gnucap": ("simulators", Simulator.GNUCAP),
    "xschem": ("schematic_editors", SchematicEditor.XSCHEM),
    "qucs-s": ("schematic_editors", SchematicEditor.QUCS_S),
    "klayout": ("layout_editors", LayoutEditor.KLAYOUT),
    "magic": ("layout_editors", LayoutEditor.MAGIC),
}


def parse_eda_config(raw_value: str) -> tuple[list[Simulator], list[SchematicEditor], list[LayoutEditor]]:
    simulators: list[Simulator] = []
    schematic_editors: list[SchematicEditor] = []
    layout_editors: list[LayoutEditor] = []

    tokens = [token.strip() for token in raw_value.split(",") if token.strip()]
    if not tokens:
        raise ValueError("--eda-config must include at least one tool.")

    for token in tokens:
        mapped = EDA_CONFIG_MAP.get(token.lower())
        if not mapped:
            choices = ", ".join(sorted(EDA_CONFIG_MAP))
            raise ValueError(f"Unknown EDA config tool '{token}'. Supported values: {choices}")
        target_attr, enum_value = mapped
        target_list = {
            "simulators": simulators,
            "schematic_editors": schematic_editors,
            "layout_editors": layout_editors,
        }[target_attr]
        if enum_value not in target_list:
            target_list.append(enum_value)

    return simulators, schematic_editors, layout_editors


def build_config_from_args(args: Namespace, pdk_root: str) -> InstallConfig:
    config = InstallConfig()
    config.pdk_root = pdk_root

    if getattr(args, "pdk", None):
        config.pdk = PDKChoice(args.pdk)
    if getattr(args, "mode", None):
        config.install_mode = InstallMode(args.mode)
    if getattr(args, "source", None):
        config.pdk_source_type = PDKSourceType(args.source)
    if getattr(args, "install_dir", None):
        config.install_dir = args.install_dir
    if getattr(args, "local_source", None):
        config.local_source_root = args.local_source
    if getattr(args, "github_commit", None):
        config.github_source_mode = GitHubSourceMode.COMMIT
        config.github_commit = args.github_commit
    elif getattr(args, "github_branch", None):
        config.github_source_mode = GitHubSourceMode.BRANCH
        config.github_branch = args.github_branch
    if getattr(args, "fetch_dependencies_from_github", False):
        config.fetch_dependencies_from_github = True
    if getattr(args, "override_sg13g2", False):
        config.override_existing_sg13g2 = True
    if getattr(args, "skip_tool_check", False):
        config.skip_tool_check = True
    if getattr(args, "no_compile_verilog_a", False):
        config.compile_verilog_a = False
    if getattr(args, "eda_config", None):
        sims, sch, lay = parse_eda_config(args.eda_config)
        config.simulators = sims
        config.schematic_editors = sch
        config.layout_editors = lay

    return config


def _get_install_destination_row(plan) -> EnvCheckResult | None:
    return next((row for row in plan.env_checks if row.variable == "Install Destination"), None)


def _get_override_destination_rows(plan) -> list[EnvCheckResult]:
    return [
        row for row in plan.env_checks
        if row.requires_confirmation and row.reason_code == "install_destination_override"
    ]


def _validate_config_source(config: InstallConfig) -> tuple[bool, str]:
    return validate_source_with_dependencies(config)


def run_nogui_install(args: Namespace, pdk_root: str, stdout=None, stderr=None) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    config = build_config_from_args(args, pdk_root)

    ok, message = _validate_config_source(config)
    if not ok:
        print(f"ERROR: {message}", file=stderr, flush=True)
        return 1

    plan = build_install_plan(config)
    print(plan.to_markdown(), file=stdout, flush=True)

    override_rows = _get_override_destination_rows(plan)
    if override_rows and not getattr(args, "allow_override", False):
        destinations = ", ".join(
            row.expected_value or row.current_value or "" for row in override_rows
        )
        print(
            f"ERROR: Installation would override existing destinations: {destinations}",
            file=stderr,
            flush=True,
        )
        print("Re-run with --allow-override to replace that destination.", file=stderr, flush=True)
        return 2

    if plan.has_errors():
        print("ERROR: Installation plan contains blocking errors.", file=stderr, flush=True)
        return 1

    executor = InstallExecutor(plan)
    executor.log_line.connect(lambda line: print(line, file=stdout, flush=True))
    executor.run()

    success = all(step.status != ExecStepStatus.FAILED for step in executor.steps) and not executor._cancelled
    if success:
        print("Installation completed successfully!", file=stdout, flush=True)
        return 0

    print("Installation completed with errors.", file=stderr, flush=True)
    return 1
