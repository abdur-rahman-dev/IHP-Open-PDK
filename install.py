#!/usr/bin/env python3

import sys
import os

PDK_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PDK_ROOT)


def main():
    parser = argparse.ArgumentParser(
        description="IHP-Open-PDK Installer",
    )
    parser.add_argument(
        "--cli", action="store_true",
        help="Run in CLI mode (no GUI)",
    )
    args, remaining = parser.parse_known_args()

    if args.cli:
        from installer.backend.checker import build_install_plan
        from installer.backend.models import InstallConfig
        config = InstallConfig()
        config.pdk_root = PDK_ROOT
        plan = build_install_plan(config)
        print(plan.to_markdown())
        return

    from PySide6.QtWidgets import QApplication
    from installer.frontend.main_window import MainWindow

    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    import argparse
    main()
