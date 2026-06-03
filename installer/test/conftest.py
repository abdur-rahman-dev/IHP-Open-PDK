import os
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from installer.backend.models import InstallConfig, PDKChoice
from installer.frontend.theme import ThemeManager


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def fake_pdk_root(tmp_path: Path) -> Path:
    root = tmp_path / "IHP-Open-PDK"
    pdk_dir = root / "ihp-sg13g2"

    paths = [
        pdk_dir / "libs.tech" / "ngspice" / "models",
        pdk_dir / "libs.tech" / "ngspice" / "osdi",
        pdk_dir / "libs.tech" / "xyce" / "models",
        pdk_dir / "libs.tech" / "xyce" / "plugins",
        pdk_dir / "libs.tech" / "gnucap",
        pdk_dir / "libs.tech" / "klayout",
        pdk_dir / "libs.tech" / "qucs-s",
        pdk_dir / "libs.tech" / "xschem",
        pdk_dir / "libs.tech" / "verilog-a" / "psp103",
        pdk_dir / "libs.tech" / "verilog-a" / "r3_cmc",
        pdk_dir / "libs.tech" / "verilog-a" / "mosvar",
        pdk_dir / "libs.ref" / "sg13g2_stdcell" / "spice",
        pdk_dir / "libs.ref" / "sg13g2_io" / "spice",
    ]
    for path in paths:
        path.mkdir(parents=True, exist_ok=True)

    (pdk_dir / "libs.tech" / "ngspice" / ".spiceinit").write_text("* fake spiceinit\n")
    (root / "versions.txt").write_text(
        "Python 3.10.12\n"
        "openvaf 23.5.0\n"
        "ngspice 43\n"
        "Xyce 7.8-opensource\n"
        "xschem 3.4.6\n"
        "qucs-s s25.2.0\n"
        "klayout 0.30.3\n"
        "openEMS v0.0.35-108-gc651cce\n"
        "magic 8.3.589\n"
    )
    return root


@pytest.fixture
def fake_home(tmp_path: Path) -> Path:
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    (home / ".bashrc").write_text("# test bashrc\n")
    return home


@pytest.fixture
def mock_env(monkeypatch: pytest.MonkeyPatch, fake_pdk_root: Path, fake_home: Path):
    monkeypatch.setenv("PDK_ROOT", str(fake_pdk_root))
    monkeypatch.setenv("PDK", "ihp-sg13g2")
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    return {
        "PDK_ROOT": str(fake_pdk_root),
        "PDK": "ihp-sg13g2",
        "HOME": str(fake_home),
    }


@pytest.fixture
def install_config(fake_pdk_root: Path, mock_env) -> InstallConfig:
    cfg = InstallConfig()
    cfg.pdk = PDKChoice.SG13G2
    cfg.pdk_root = str(fake_pdk_root)
    return cfg


@pytest.fixture
def app(qtbot):
    return QApplication.instance()


@pytest.fixture
def theme_manager(app) -> ThemeManager:
    return ThemeManager(app, initial="light")
