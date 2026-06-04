import importlib.metadata
import os
import subprocess
import sys
import types

from installer.backend import checker
from installer.backend.checker import (
    _check_selected_tools,
    check_environment,
    check_klayout_python,
    check_tools_for_names,
    check_tools,
    get_github_repo_url,
    get_version,
    get_which_path,
    is_program_installed,
    parse_version,
    validate_github_source,
    validate_local_source,
    version_gte,
)
from installer.backend.models import GitHubSourceMode, InstallConfig, InstallMode, LayoutEditor, PDKChoice, PDKSourceType, Simulator, ToolInfo, ToolStatusEnum


class _RunResult:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_is_program_installed_true(monkeypatch):
    def fake_run(*args, **kwargs):
        return _RunResult(returncode=0, stdout="/usr/bin/python3\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert is_program_installed("python3") is True


def test_is_program_installed_false(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert is_program_installed("missing-tool") is False


def test_get_version_unsafe_tool_returns_none():
    assert get_version("some-random-tool") is None


def test_get_which_path_returns_path(monkeypatch):
    def fake_run(*args, **kwargs):
        return _RunResult(returncode=0, stdout="/usr/bin/python3\n")

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert get_which_path("python3") == "/usr/bin/python3"


def test_get_which_path_returns_none_on_error(monkeypatch):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(subprocess, "run", fake_run)

    assert get_which_path("missing-tool") is None


def test_parse_version_and_version_gte():
    assert parse_version("0.30.5") == (0, 30, 5)
    assert parse_version("43") == (43,)
    assert version_gte("3.12.3", "3.9") is True
    assert version_gte("0.29.0", "0.30.0") is False


def test_check_klayout_python_found(monkeypatch):
    fake_module = types.SimpleNamespace(__file__="/tmp/site-packages/klayout/__init__.py")
    monkeypatch.setitem(sys.modules, "klayout", fake_module)
    monkeypatch.setattr(importlib.metadata, "version", lambda name: "0.30.8")

    installed, version, path = check_klayout_python()

    assert installed is True
    assert version == "0.30.8"
    assert path == "/tmp/site-packages/klayout/__init__.py"


def test_check_klayout_python_not_found(monkeypatch):
    monkeypatch.delitem(sys.modules, "klayout", raising=False)

    real_import = __import__

    def fake_import(name, *args, **kwargs):
        if name == "klayout":
            raise ImportError("missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", fake_import)

    installed, version, path = check_klayout_python()

    assert installed is False
    assert version is None
    assert path is None


def test_check_tools_ngspice_config(monkeypatch, install_config):
    install_config.simulators = [Simulator.NGSPICE]

    versions = {
        "openvaf-r": "23.5.0",
        "python3": "3.12.3",
        "ngspice": "43",
        "xschem": "3.4.8",
        "klayout": "0.30.3",
        "pip": "24.0",
    }
    installed = set(versions)

    monkeypatch.setattr(checker, "is_program_installed", lambda name: name in installed)
    monkeypatch.setattr(checker, "get_version", lambda name: versions.get(name))
    monkeypatch.setattr(checker, "get_which_path", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(checker, "check_klayout_python", lambda: (False, None, None))

    tools = check_tools(install_config)
    names = {tool.name for tool in tools}

    assert "openvaf-r" in names
    assert "ngspice" in names
    assert "python3" in names
    assert "pip" in names


def test_check_tools_klayout_python_mismatch(monkeypatch, install_config):
    install_config.layout_editors = [LayoutEditor.KLAYOUT]

    versions = {
        "openvaf-r": "23.5.0",
        "python3": "3.12.3",
        "ngspice": "43",
        "xschem": "3.4.8",
        "klayout": "0.30.5",
        "pip": "24.0",
    }
    installed = set(versions)

    monkeypatch.setattr(checker, "is_program_installed", lambda name: name in installed)
    monkeypatch.setattr(checker, "get_version", lambda name: versions.get(name))
    monkeypatch.setattr(checker, "get_which_path", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(
        checker,
        "check_klayout_python",
        lambda: (True, "0.30.8", "/tmp/site-packages/klayout/__init__.py"),
    )

    tools = check_tools(install_config)
    klayout_python = next(tool for tool in tools if tool.name == "klayout-python")

    assert klayout_python.status == ToolStatusEnum.WARNING
    assert "Version mismatch" in klayout_python.message


def test_check_environment_spiceinit_missing(monkeypatch, fake_pdk_root, fake_home):
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root)

    spiceinit = fake_home / ".spiceinit"
    if spiceinit.exists() or spiceinit.is_symlink():
        spiceinit.unlink()

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("PDK_ROOT", str(fake_pdk_root))
    monkeypatch.setenv("PDK", "ihp-sg13g2")

    results = check_environment(cfg)
    spiceinit_row = next(item for item in results if item.variable == ".spiceinit")

    assert spiceinit_row.is_set is False
    assert spiceinit_row.current_value is None
    assert spiceinit_row.action == "Will create symlink"


def test_check_environment_spiceinit_valid(monkeypatch, fake_pdk_root, fake_home):
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root)

    src = fake_pdk_root / "ihp-sg13g2" / "libs.tech" / "ngspice" / ".spiceinit"
    dst = fake_home / ".spiceinit"
    if dst.exists() or dst.is_symlink():
        dst.unlink()
    os.symlink(src, dst)

    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setenv("PDK_ROOT", str(fake_pdk_root))
    monkeypatch.setenv("PDK", "ihp-sg13g2")

    results = check_environment(cfg)
    spiceinit_row = next(item for item in results if item.variable == ".spiceinit")

    assert spiceinit_row.is_set is True
    assert spiceinit_row.action == "Valid symlink"


def test_validate_local_source_ok(fake_pdk_root):
    cfg = InstallConfig()
    cfg.local_source_root = str(fake_pdk_root)

    ok, message = validate_local_source(cfg)

    assert ok is True
    assert message == ""


def test_validate_local_source_reports_missing_paths(tmp_path):
    cfg = InstallConfig()
    cfg.local_source_root = str(tmp_path)

    ok, message = validate_local_source(cfg)

    assert ok is False
    assert "libs.tech" in message
    assert "libs.ref" in message


def test_get_github_repo_url_by_pdk():
    cfg = InstallConfig()
    assert get_github_repo_url(cfg).endswith("IHP-Open-PDK.git")
    cfg.pdk = PDKChoice.SG13CMOS5L
    assert get_github_repo_url(cfg).endswith("ihp-sg13cmos5l.git")


def test_validate_github_source_reports_missing_git(monkeypatch):
    cfg = InstallConfig()
    monkeypatch.setattr(checker, "is_program_installed", lambda name: False)

    ok, message = validate_github_source(cfg)

    assert ok is False
    assert "From Local" in message


def test_validate_github_source_accepts_branch(monkeypatch):
    cfg = InstallConfig()
    cfg.github_branch = "dev"
    monkeypatch.setattr(checker, "is_program_installed", lambda name: True)

    def fake_run(*args, **kwargs):
        return _RunResult(stdout="abc123\trefs/heads/dev\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, message = validate_github_source(cfg)

    assert ok is True
    assert message == ""


def test_validate_github_source_commit_mode_empty_uses_fallback_branch(monkeypatch):
    cfg = InstallConfig()
    cfg.github_source_mode = GitHubSourceMode.COMMIT
    monkeypatch.setattr(checker, "is_program_installed", lambda name: True)

    def fake_run(*args, **kwargs):
        return _RunResult(stdout="abc123\trefs/heads/dev\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, message = validate_github_source(cfg)

    assert ok is True
    assert message == ""


def test_validate_github_source_rejects_missing_commit(monkeypatch):
    cfg = InstallConfig()
    cfg.github_source_mode = GitHubSourceMode.COMMIT
    cfg.github_commit = "deadbeef"
    monkeypatch.setattr(checker, "is_program_installed", lambda name: True)

    def fake_run(*args, **kwargs):
        return _RunResult(stdout="abc123\trefs/heads/dev\n", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)

    ok, message = validate_github_source(cfg)

    assert ok is False
    assert "deadbeef" in message


def test_check_selected_tools_preserves_klayout_python(monkeypatch, install_config):
    install_config.tools_to_check = ["klayout"]

    monkeypatch.setattr(
        checker,
        "check_tools",
        lambda cfg: [
            ToolInfo(name="klayout", installed=True),
            ToolInfo(name="klayout-python", installed=True),
            ToolInfo(name="python3", installed=True),
        ],
    )

    results = _check_selected_tools(install_config)
    names = [tool.name for tool in results]

    assert "klayout" in names
    assert "klayout-python" in names
    assert "python3" not in names


def test_check_tools_for_names_is_independent_of_eda_config(monkeypatch, install_config):
    install_config.simulators = []
    install_config.schematic_editors = []
    install_config.layout_editors = []

    monkeypatch.setattr(
        checker,
        "check_tools",
        lambda cfg: [
            ToolInfo(name="openvaf-r", installed=True),
            ToolInfo(name="python3", installed=True),
            ToolInfo(name="pip", installed=True),
            ToolInfo(name="klayout", installed=True),
            ToolInfo(name="klayout-python", installed=True),
        ],
    )

    results = check_tools_for_names(["klayout"], install_config)
    names = [tool.name for tool in results]

    assert names == ["klayout", "klayout-python"]


def test_check_environment_install_destination_override_for_nonempty_dir(monkeypatch, fake_pdk_root, fake_home):
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root)
    cfg.install_mode = InstallMode.NEW
    cfg.install_dir = str(fake_pdk_root / "target-root")
    dest = fake_pdk_root / "target-root" / "ihp-sg13g2"
    dest.mkdir(parents=True)
    (dest / "existing.txt").write_text("present\n")

    monkeypatch.setenv("HOME", str(fake_home))
    results = check_environment(cfg)
    row = next(item for item in results if item.variable == "Install Destination")

    assert row.current_value == str(dest)
    assert "overridden with new contents from local source" in row.action


def test_check_environment_install_destination_uses_github_wording(monkeypatch, fake_pdk_root, fake_home):
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root)
    cfg.install_mode = InstallMode.NEW
    cfg.install_dir = str(fake_pdk_root / "target-root")
    cfg.pdk_source_type = PDKSourceType.GITHUB

    monkeypatch.setenv("HOME", str(fake_home))
    results = check_environment(cfg)
    row = next(item for item in results if item.variable == "Install Destination")

    assert "GitHub source" in row.action


def test_check_environment_change_mode_omits_destination_row(monkeypatch, fake_pdk_root, fake_home):
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root)
    cfg.install_mode = InstallMode.CHANGE
    cfg.install_dir = str(fake_pdk_root)

    monkeypatch.setenv("HOME", str(fake_home))
    results = check_environment(cfg)

    assert all(item.variable != "Install Destination" for item in results)
