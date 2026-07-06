import os
from pathlib import Path

from installer.backend.executor import InstallExecutor
from installer.backend.models import ExecStep, GitHubSourceMode, InstallConfig, InstallPlan, LayoutEditor, PDKChoice, PDKSourceType, Simulator, ToolInfo


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


def test_build_steps_adds_fetch_for_github_source(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.install_dir = str(fake_pdk_root / "custom-root")
    plan.config.pdk_source_type = PDKSourceType.GITHUB

    executor = InstallExecutor(plan)
    executor._build_steps()
    labels = [step.label for step in executor.steps]

    assert labels[0] == "Fetch PDK source from GitHub"
    assert any(label.startswith("Copy PDK to") for label in labels)


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


def test_copy_step_replaces_existing_destination_symlink_collision(fake_pdk_root, fake_home):
    source_link_dir = fake_pdk_root / "ihp-sg13g2" / "libs.tech" / "ngspice"
    source_link = source_link_dir / "install.py"
    os.symlink("../xschem/install.py", source_link)

    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.install_dir = str(fake_pdk_root / "custom-root")
    executor = InstallExecutor(plan)
    dest = fake_pdk_root / "custom-root" / "ihp-sg13g2"
    collision = dest / "libs.tech" / "ngspice"
    collision.mkdir(parents=True)
    os.symlink("old-target", collision / "install.py")
    (dest / "stale.txt").write_text("old\n")

    ok = executor._exec_step(0, ExecStep(f"Copy PDK to {dest}"))

    assert ok is True
    assert not (dest / "stale.txt").exists()
    assert os.path.islink(dest / "libs.tech" / "ngspice" / "install.py")
    assert os.readlink(dest / "libs.tech" / "ngspice" / "install.py") == "../xschem/install.py"


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


def test_github_needs_submodules_for_sg13g2_dev(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.pdk_source_type = PDKSourceType.GITHUB
    plan.config.github_branch = "dev"
    executor = InstallExecutor(plan)

    assert executor._github_needs_submodules() is True


def test_github_needs_submodules_false_for_cmos5l_main(fake_pdk_root, fake_home):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.pdk = PDKChoice.SG13CMOS5L
    plan.config.pdk_source_type = PDKSourceType.GITHUB
    plan.config.github_branch = "main"
    executor = InstallExecutor(plan)

    assert executor._github_needs_submodules() is False


def test_fetch_github_source_branch_uses_recurse_for_sg13g2_dev(fake_pdk_root, fake_home, monkeypatch, tmp_path):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.pdk_source_type = PDKSourceType.GITHUB
    plan.config.github_branch = "dev"
    executor = InstallExecutor(plan)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    (clone_dir / "ihp-sg13g2" / "libs.tech").mkdir(parents=True)
    monkeypatch.setattr("installer.backend.executor.tempfile.mkdtemp", lambda prefix: str(clone_dir))

    seen = []

    def fake_run_cmd(cmd, cwd=None):
        seen.append((cmd, cwd))
        return True, "ok"

    monkeypatch.setattr(executor, "_run_cmd", fake_run_cmd)

    ok = executor._fetch_github_source()

    assert ok is True
    assert "--recurse-submodules" in seen[0][0]
    assert executor._resolved_source_pdk_dir == str(clone_dir / "ihp-sg13g2")


def test_resolve_cloned_source_pdk_dir_accepts_direct_pdk_layout(fake_pdk_root, fake_home, tmp_path):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.pdk = PDKChoice.SG13CMOS5L
    executor = InstallExecutor(plan)
    clone_dir = tmp_path / "clone"
    (clone_dir / "libs.tech").mkdir(parents=True)

    assert executor._resolve_cloned_source_pdk_dir(str(clone_dir)) == str(clone_dir)


def test_fetch_github_source_commit_runs_checkout_and_submodules(fake_pdk_root, fake_home, monkeypatch, tmp_path):
    plan = _make_plan(fake_pdk_root, fake_home)
    plan.config.pdk_source_type = PDKSourceType.GITHUB
    plan.config.github_source_mode = GitHubSourceMode.COMMIT
    plan.config.github_commit = "deadbeef"
    plan.config.resolved_github_commit = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    executor = InstallExecutor(plan)
    clone_dir = tmp_path / "clone"
    clone_dir.mkdir()
    (clone_dir / "ihp-sg13g2" / "libs.tech").mkdir(parents=True)
    monkeypatch.setattr("installer.backend.executor.tempfile.mkdtemp", lambda prefix: str(clone_dir))

    seen = []

    def fake_run_cmd(cmd, cwd=None):
        seen.append((cmd, cwd))
        return True, "ok"

    monkeypatch.setattr(executor, "_run_cmd", fake_run_cmd)

    ok = executor._fetch_github_source()

    assert ok is True
    assert any(cmd == "git checkout deadbeefdeadbeefdeadbeefdeadbeefdeadbeef" for cmd, _ in seen)
    assert any(cmd == "git submodule update --init --recursive" for cmd, _ in seen)


def test_cleanup_temp_source_removes_directory(fake_pdk_root, fake_home, tmp_path):
    plan = _make_plan(fake_pdk_root, fake_home)
    executor = InstallExecutor(plan)
    temp_dir = tmp_path / "temp-src"
    temp_dir.mkdir()
    (temp_dir / "file.txt").write_text("x")
    executor._temp_source_root = str(temp_dir)
    executor._resolved_source_pdk_dir = str(temp_dir)

    executor._cleanup_temp_source()

    assert not temp_dir.exists()
    assert executor._temp_source_root is None
    assert executor._resolved_source_pdk_dir is None


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
