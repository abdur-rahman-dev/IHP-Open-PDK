import os
import subprocess
import sys
import textwrap
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


def test_main_window_close_exits_cleanly_from_idle_state(installer_worktree: Path):
    script = textwrap.dedent(
        f"""
        import os
        import sys
        from pathlib import Path
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        repo = Path(r"{installer_worktree}")
        sys.path.insert(0, str(repo))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from installer.frontend.theme import ThemeManager
        from installer.frontend.main_window import MainWindow

        app = QApplication(sys.argv)
        theme = ThemeManager(app, initial="light")
        window = MainWindow(theme)
        window.show()
        QTimer.singleShot(100, window.close)
        sys.exit(app.exec())
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=installer_worktree,
        env=_base_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0


def test_main_window_close_exits_cleanly_with_fake_running_executor(installer_worktree: Path):
    script = textwrap.dedent(
        f"""
        import os
        import sys
        from pathlib import Path
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        repo = Path(r"{installer_worktree}")
        sys.path.insert(0, str(repo))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from installer.frontend.theme import ThemeManager
        from installer.frontend.main_window import MainWindow

        class FakeExecutor:
            def isRunning(self):
                return True

            def cancel(self):
                return None

            def wait(self, timeout):
                return True

        app = QApplication(sys.argv)
        theme = ThemeManager(app, initial="light")
        window = MainWindow(theme)
        window.check_page.executor = FakeExecutor()
        window.show()
        QTimer.singleShot(100, window.close)
        sys.exit(app.exec())
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=installer_worktree,
        env=_base_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0


def test_source_validation_switch_local_to_github_reenables_next(installer_worktree: Path):
    script = textwrap.dedent(
        f"""
        import os
        import sys
        from pathlib import Path
        from PySide6.QtWidgets import QApplication

        repo = Path(r"{installer_worktree}")
        sys.path.insert(0, str(repo))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from installer.frontend.theme import ThemeManager
        import installer.frontend.main_window as mw

        mw.validate_local_source = lambda cfg: (False, "bad local")
        mw.validate_github_source = lambda cfg: (True, "")

        app = QApplication(sys.argv)
        theme = ThemeManager(app, initial="light")
        window = mw.MainWindow(theme)
        window.show()
        window.choice_page.local_source_input.setText("/tmp/invalid")
        window._refresh_source_validity()
        print("LOCAL", window.next_btn.isEnabled(), flush=True)
        window.choice_page.source_github.click()
        window._refresh_source_validity()
        print("GITHUB", window.next_btn.isEnabled(), flush=True)
        window.close()
        app.processEvents()
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=installer_worktree,
        env=_base_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert "LOCAL False" in result.stdout
    assert "GITHUB True" in result.stdout


def test_source_validation_switch_github_to_local_reenables_next(installer_worktree: Path):
    script = textwrap.dedent(
        f"""
        import os
        import sys
        from pathlib import Path
        from PySide6.QtWidgets import QApplication

        repo = Path(r"{installer_worktree}")
        sys.path.insert(0, str(repo))
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

        from installer.frontend.theme import ThemeManager
        import installer.frontend.main_window as mw

        mw.validate_local_source = lambda cfg: (True, "")
        mw.validate_github_source = lambda cfg: (False, "use local")

        app = QApplication(sys.argv)
        theme = ThemeManager(app, initial="light")
        window = mw.MainWindow(theme)
        window.show()
        window.choice_page.source_github.click()
        window._refresh_source_validity()
        print("GITHUB", window.next_btn.isEnabled(), flush=True)
        window.choice_page.source_local.click()
        window._refresh_source_validity()
        print("LOCAL", window.next_btn.isEnabled(), flush=True)
        window.close()
        app.processEvents()
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=installer_worktree,
        env=_base_env(),
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0
    assert "GITHUB False" in result.stdout
    assert "LOCAL True" in result.stdout
