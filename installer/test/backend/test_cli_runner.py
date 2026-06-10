from argparse import Namespace
import io

import pytest

from installer.backend import cli_runner
from installer.backend.models import LayoutEditor, PDKChoice, PDKSourceType, SchematicEditor, Simulator


def _args(**overrides):
    base = {
        "pdk": None,
        "mode": None,
        "source": None,
        "install_dir": None,
        "local_source_root": None,
        "github_branch": None,
        "github_commit": None,
        "skip_tool_check": False,
        "no_compile_verilog_a": False,
        "eda_config": None,
        "allow_override": False,
    }
    base.update(overrides)
    return Namespace(**base)


def test_parse_eda_config_replaces_defaults_case_insensitively():
    sims, sch, lay = cli_runner.parse_eda_config("xyce,QUCS-S,klayout")

    assert sims == [Simulator.XYCE]
    assert sch == [SchematicEditor.QUCS_S]
    assert lay == [LayoutEditor.KLAYOUT]


def test_parse_eda_config_rejects_unknown_tool():
    with pytest.raises(ValueError, match="Unknown EDA config tool"):
        cli_runner.parse_eda_config("ngspice,unknown-tool")


def test_build_config_from_args_replaces_default_eda_selection(fake_pdk_root):
    args = _args(
        pdk=PDKChoice.SG13CMOS5L.value,
        source=PDKSourceType.GITHUB.value,
        eda_config="gnucap,qucs-s,magic",
        no_compile_verilog_a=True,
    )

    config = cli_runner.build_config_from_args(args, str(fake_pdk_root))

    assert config.pdk == PDKChoice.SG13CMOS5L
    assert config.pdk_source_type == PDKSourceType.GITHUB
    assert config.simulators == [Simulator.GNUCAP]
    assert config.schematic_editors == [SchematicEditor.QUCS_S]
    assert config.layout_editors == [LayoutEditor.MAGIC]
    assert config.compile_verilog_a is False


def test_run_nogui_install_rejects_override_without_flag(fake_pdk_root, fake_home, monkeypatch, tmp_path):
    args = _args(mode="new", install_dir=str(tmp_path / "target-root"))
    destination = tmp_path / "target-root" / "ihp-sg13g2"
    destination.mkdir(parents=True)
    (destination / "existing.txt").write_text("present\n")

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr(cli_runner, "build_install_plan", lambda config: type("Plan", (), {
        "env_checks": [type("Row", (), {
            "variable": "Install Destination",
            "requires_confirmation": True,
            "reason_code": "install_destination_override",
            "expected_value": str(destination),
            "current_value": str(destination),
        })()],
        "to_markdown": lambda self: "# plan",
        "has_errors": lambda self: False,
    })())
    monkeypatch.setattr(cli_runner, "_validate_config_source", lambda config: (True, ""))

    stdout = io.StringIO()
    stderr = io.StringIO()
    rc = cli_runner.run_nogui_install(
        args,
        str(fake_pdk_root),
        stdout=stdout,
        stderr=stderr,
    )

    assert rc == 2
    assert "--allow-override" in stderr.getvalue()
