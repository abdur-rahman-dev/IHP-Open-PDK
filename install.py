#!/usr/bin/env python3

import sys
import os

PDK_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PDK_ROOT)


def main():
    import argparse
    import subprocess

    parser = argparse.ArgumentParser(
        description="IHP-Open-PDK Installer",
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in CLI mode (no GUI)",
    )
    parser.add_argument(
        "--nogui", action="store_true",
        help="Run installer in non-GUI mode",
    )
    parser.add_argument(
        "--test", nargs="?", const="", default=None,
        help="Run pytest on installer/test/ (optional: pass pytest args)",
    )
    parser.add_argument("--pdk", choices=["ihp-sg13g2", "ihp-sg13cmos5l"])
    parser.add_argument("--mode", choices=["new", "change"])
    parser.add_argument("--source", choices=["local", "github"])
    parser.add_argument("--install-dir")
    parser.add_argument("--local-source-root")
    parser.add_argument("--github-branch")
    parser.add_argument("--github-commit")
    parser.add_argument("--skip-tool-check", action="store_true")
    parser.add_argument("--no-compile-verilog-a", action="store_true")
    parser.add_argument("--eda-config")
    parser.add_argument("--allow-override", action="store_true")
    args, remaining = parser.parse_known_args()

    if args.test is not None:
        pytest_args = args.test.split() if args.test else []
        cmd = [sys.executable, "-m", "pytest"] + pytest_args
        if remaining:
            cmd += remaining
        else:
            cmd.append("installer/test/")
        return subprocess.call(cmd)

    if args.cli:
        from installer.backend.checker import build_install_plan
        from installer.backend.models import InstallConfig
        config = InstallConfig()
        config.pdk_root = PDK_ROOT
        plan = build_install_plan(config)
        print(plan.to_markdown())
        return 0

    if args.nogui:
        from installer.backend.cli_runner import run_nogui_install

        return run_nogui_install(args, PDK_ROOT)

    from PySide6.QtWidgets import QApplication
    from installer.frontend.main_window import MainWindow
    from installer.frontend.theme import ThemeManager

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(True)

    theme_manager = ThemeManager(app, initial="light")

    window = MainWindow(theme_manager)
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
