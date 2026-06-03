import os
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]


def _base_env():
    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
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
