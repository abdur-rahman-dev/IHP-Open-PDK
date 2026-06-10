import os
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _base_env():
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    return env


def _with_home(base_env, home_dir: Path):
    env = base_env.copy()
    env["HOME"] = str(home_dir)
    return env


@pytest.fixture
def installer_worktree(tmp_path: Path):
    worktree = tmp_path / "installer-worktree"
    subprocess.run(
        ["git", "-C", str(REPO_ROOT), "worktree", "add", "--detach", str(worktree), "installer"],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        yield worktree
    finally:
        subprocess.run(
            ["git", "-C", str(REPO_ROOT), "worktree", "remove", "--force", str(worktree)],
            check=False,
            capture_output=True,
            text=True,
        )


def test_install_cli_runs_and_prints_expected_sections(installer_worktree: Path):
    result = subprocess.run(
        [sys.executable, "install.py", "--cli"],
        cwd=installer_worktree,
        env=_base_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0
    assert "## Configuration" in result.stdout
    assert "## Tool Check Results" in result.stdout
    assert "## Environment Variables" in result.stdout
    assert "## Planned Actions" in result.stdout


def test_install_test_delegates_to_pytest(installer_worktree: Path):
    result = subprocess.run(
        [
            sys.executable,
            "install.py",
            "--test=-q",
            "installer/test/backend/test_models.py",
        ],
        cwd=installer_worktree,
        env=_base_env(),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 0
    assert "passed" in result.stdout or "passed" in result.stderr


def test_install_nogui_change_mode_runs_successfully(installer_worktree: Path):
    with TemporaryDirectory() as home_tmp:
        home = Path(home_tmp)
        (home / ".bashrc").write_text("# test bashrc\n")

        result = subprocess.run(
            [
                sys.executable,
                "install.py",
                "--nogui",
                "--mode",
                "change",
                "--source",
                "local",
                "--local-source-root",
                str(installer_worktree),
            ],
            cwd=installer_worktree,
            env=_with_home(_base_env(), home),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0
        assert "Installation completed successfully!" in result.stdout
        assert (home / ".spiceinit").is_symlink()


def test_install_nogui_eda_config_replaces_defaults(installer_worktree: Path):
    with TemporaryDirectory() as home_tmp:
        home = Path(home_tmp)
        (home / ".bashrc").write_text("# test bashrc\n")

        result = subprocess.run(
            [
                sys.executable,
                "install.py",
                "--nogui",
                "--mode",
                "change",
                "--source",
                "local",
                "--local-source-root",
                str(installer_worktree),
                "--eda-config",
                "Xyce,qucs-s,magic",
            ],
            cwd=installer_worktree,
            env=_with_home(_base_env(), home),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        assert result.returncode == 0
        assert "| Simulators | Xyce |" in result.stdout
        assert "| Schematic Editors | qucs-s |" in result.stdout
        assert "| Layout Editors | magic |" in result.stdout


def test_install_nogui_rejects_override_without_flag(installer_worktree: Path, tmp_path: Path):
    home = tmp_path / "home"
    home.mkdir()
    (home / ".bashrc").write_text("# test bashrc\n")
    target_root = tmp_path / "target-root"
    target_pdk_dir = target_root / "ihp-sg13g2"
    target_pdk_dir.mkdir(parents=True)
    (target_pdk_dir / "existing.txt").write_text("present\n")

    result = subprocess.run(
        [
            sys.executable,
            "install.py",
            "--nogui",
            "--mode",
            "new",
            "--source",
            "local",
            "--local-source-root",
            str(installer_worktree),
            "--install-dir",
            str(target_root),
        ],
        cwd=installer_worktree,
        env=_with_home(_base_env(), home),
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )

    assert result.returncode == 2
    assert "--allow-override" in result.stderr
