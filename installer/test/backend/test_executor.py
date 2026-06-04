import os
from pathlib import Path

from installer.backend.executor import InstallExecutor
from installer.backend.models import ExecStep, InstallConfig, InstallPlan, LayoutEditor, Simulator, ToolInfo


def _make_plan(fake_pdk_root: Path, fake_home: Path) -> InstallPlan:
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root)
    cfg.install_dir = str(fake_pdk_root)
    os.environ["HOME"] = str(fake_home)
    return InstallPlan(config=cfg, pdk_root=str(fake_pdk_root))


def test_build_steps_includes_copy_and_update_when_target_differs(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.install_dir = str(fake_pdk_root / "custom-root")
    plan.tools = [
        ToolInfo(name="openvaf-r", installed=True),
        ToolInfo(name="qucs-s", installed=True),
    ]

    executor = InstallExecutor(plan)
    executor._build_steps()
    labels = [step.label for step in executor.steps]

    assert any(label.startswith("Copy PDK to") for label in labels)
    assert "Update PDK_ROOT" in labels


def test_build_steps_no_copy_when_target_matches_source(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.tools = [ToolInfo(name="openvaf-r", installed=True)]

    executor = InstallExecutor(plan)
    executor._build_steps()
    labels = [step.label for step in executor.steps]

    assert not any(label.startswith("Copy PDK to") for label in labels)
    assert "Update PDK_ROOT" not in labels


def test_copy_step_overrides_existing_destination(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.install_dir = str(fake_pdk_root / "custom-root")
    executor = InstallExecutor(plan)
    dest = fake_pdk_root / "custom-root" / "ihp-sg13g2"
    dest.mkdir(parents=True)
    (dest / "stale.txt").write_text("old\n")

    ok = executor._exec_step(0, ExecStep(f"Copy PDK to {dest}"))

    assert ok is True
    assert (dest / "libs.tech").exists()


def test_build_steps_respects_compile_verilog_a_flag(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.compile_verilog_a = False
    plan.config.simulators = [Simulator.NGSPICE, Simulator.XYCE, Simulator.GNUCAP]
    plan.tools = [
        ToolInfo(name="openvaf-r", installed=True),
        ToolInfo(name="Xyce", installed=True),
        ToolInfo(name="buildxyceplugin", installed=True),
        ToolInfo(name="gnucap", installed=True),
        ToolInfo(name="gnucap-mg-vams", installed=True),
    ]

    executor = InstallExecutor(plan)
    executor._build_steps()
    labels = [step.label for step in executor.steps]

    assert not any(label.startswith("Compile OSDI:") for label in labels)
    assert not any(label.startswith("Compile Xyce plugin:") for label in labels)
    assert not any(label.startswith("Compile gnucap plugin:") for label in labels)


def test_write_env_creates_marked_block(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    executor = InstallExecutor(plan)

    ok = executor._write_env(str(fake_pdk_root), "ihp-sg13g2")
    content = (fake_home / ".bashrc").read_text()

    assert ok is True
    assert "# >>> IHP-Open-PDK >>>" in content
    assert 'export PDK_ROOT="' in content
    assert 'export PDK="ihp-sg13g2"' in content


def test_write_env_skips_existing_block(fake_pdk_root, fake_home):
    bashrc = fake_home / ".bashrc"
    bashrc.write_text("# >>> IHP-Open-PDK >>>\nold\n# <<< IHP-Open-PDK <<<\n")

    plan = _make_plan(fake_pdk_root, fake_home)
    executor = InstallExecutor(plan)

    ok = executor._write_env(str(fake_pdk_root), "ihp-sg13g2")

    assert ok is True
    assert bashrc.read_text().count("# >>> IHP-Open-PDK >>>") == 1


def test_write_env_sets_klayout_vars_when_selected(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.layout_editors = [LayoutEditor.KLAYOUT]
    executor = InstallExecutor(plan)

    executor._write_env(str(fake_pdk_root), "ihp-sg13g2")
    content = (fake_home / ".bashrc").read_text()

    assert "KLAYOUT_PATH" in content
    assert "KLAYOUT_HOME" in content


def test_exec_step_skips_when_spiceinit_is_regular_file(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    executor = InstallExecutor(plan)
    dst = fake_home / ".spiceinit"
    dst.write_text("regular file\n")

    logs = []
    executor.log_line.connect(logs.append)

    ok = executor._exec_step(0, ExecStep("Create .spiceinit symlink"))

    assert ok is True
    assert any("not a symlink" in line for line in logs)


def test_run_cmd_success(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    executor = InstallExecutor(plan)

    ok, output = executor._run_cmd("python3 -c \"print('hello')\"")

    assert ok is True
    assert "hello" in output


def test_run_emits_blank_line_and_step_header(fake_pdk_root, fake_home, monkeypatch):
    plan = _make_plan(fake_pdk_root, fake_home)
    executor = InstallExecutor(plan)
    logs = []
    executor.log_line.connect(logs.append)

    monkeypatch.setattr(executor, "_build_steps", lambda: executor.steps.extend([ExecStep("Demo step")]))
    monkeypatch.setattr(executor, "_exec_step", lambda idx, step: True)

    executor.run()

    assert logs[0] == ""
    assert logs[1] == "Step 1: Demo step"
