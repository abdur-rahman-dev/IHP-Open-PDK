from installer.backend.models import (
    GitHubSourceMode,
    InstallConfig,
    InstallPlan,
    PDKChoice,
    PDKSourceType,
    ToolInfo,
    ToolStatusEnum,
)


def test_install_config_defaults():
    cfg = InstallConfig()

    assert cfg.pdk == PDKChoice.SG13G2
    assert cfg.compile_verilog_a is True
    assert cfg.skip_tool_check is False
    assert cfg.pdk_source_type == PDKSourceType.LOCAL
    assert cfg.github_source_mode == GitHubSourceMode.BRANCH
    assert len(cfg.simulators) == 1
    assert len(cfg.schematic_editors) == 1
    assert len(cfg.layout_editors) == 1


def test_get_source_pdk_root_prefers_config(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.pdk_root = str(fake_pdk_root / "custom-root")

    assert cfg.get_source_pdk_root() == str(fake_pdk_root / "custom-root")


def test_get_source_pdk_root_falls_back_to_env(fake_pdk_root, mock_env):
    cfg = InstallConfig()

    assert cfg.get_source_pdk_root() == str(fake_pdk_root)


def test_get_source_pdk_root_prefers_local_source_root(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.local_source_root = str(fake_pdk_root / "ihp-sg13g2")

    assert cfg.get_source_pdk_root() == str(fake_pdk_root)


def test_get_local_source_pdk_dir(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.local_source_root = str(fake_pdk_root / "ihp-sg13g2")

    assert cfg.get_local_source_pdk_dir() == str(fake_pdk_root / "ihp-sg13g2")


def test_get_source_pdk_root_uses_parent_of_selected_pdk_dir(tmp_path):
    cfg = InstallConfig()
    pdk_dir = tmp_path / "some-root" / "ihp-sg13g2"
    cfg.local_source_root = str(pdk_dir)

    assert cfg.get_source_pdk_root() == str(tmp_path / "some-root")


def test_get_default_github_branch():
    cfg = InstallConfig()

    assert cfg.get_default_github_branch() == "dev"

    cfg.pdk = PDKChoice.SG13CMOS5L
    assert cfg.get_default_github_branch() == "main"


def test_get_effective_github_ref_uses_branch_or_commit_fallback():
    cfg = InstallConfig()
    cfg.github_branch = "main"
    assert cfg.get_effective_github_ref() == "main"

    cfg.github_source_mode = GitHubSourceMode.COMMIT
    cfg.github_commit = "abc123"
    assert cfg.get_effective_github_ref() == "abc123"

    cfg.github_commit = ""
    assert cfg.get_effective_github_ref() == "dev"

    cfg.pdk = PDKChoice.SG13CMOS5L
    assert cfg.get_effective_github_ref() == "main"


def test_get_effective_simulators_defaults_to_ngspice_for_compile_va():
    cfg = InstallConfig()
    cfg.simulators = []
    cfg.compile_verilog_a = True

    assert [sim.value for sim in cfg.get_effective_simulators()] == ["ngspice"]


def test_get_effective_simulators_can_be_empty_when_compile_va_disabled():
    cfg = InstallConfig()
    cfg.simulators = []
    cfg.compile_verilog_a = False

    assert cfg.get_effective_simulators() == []


def test_get_target_pdk_root_strips_pdk_suffix(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.install_dir = str(fake_pdk_root / "ihp-sg13g2")

    assert cfg.get_target_pdk_root() == str(fake_pdk_root)


def test_get_target_pdk_dir_appends_pdk(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.install_dir = str(fake_pdk_root)

    assert cfg.get_target_pdk_dir() == str(fake_pdk_root / "ihp-sg13g2")


def test_get_target_pdk_dir_keeps_existing_pdk_dir(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.install_dir = str(fake_pdk_root / "ihp-sg13g2")

    assert cfg.get_target_pdk_dir() == str(fake_pdk_root / "ihp-sg13g2")


def test_get_target_pdk_dir_no_duplicate_pdk_segment(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.install_dir = str(fake_pdk_root / "ihp-sg13g2")

    result = cfg.get_target_pdk_dir()

    assert "ihp-sg13g2/ihp-sg13g2" not in result


def test_get_target_pdk_dir_cmos5l(fake_pdk_root, mock_env):
    cfg = InstallConfig()
    cfg.pdk = PDKChoice.SG13CMOS5L
    cfg.install_dir = str(fake_pdk_root)

    assert cfg.get_target_pdk_dir() == str(fake_pdk_root / "ihp-sg13cmos5l")


def test_tool_info_install_path_field():
    tool = ToolInfo(name="python3", install_path="/usr/bin/python3")

    assert tool.install_path == "/usr/bin/python3"


def test_install_plan_has_errors_from_tool_status():
    plan = InstallPlan(
        config=InstallConfig(),
        tools=[ToolInfo(name="openvaf", status=ToolStatusEnum.ERROR)],
    )

    assert plan.has_errors() is True


def test_install_plan_has_warnings_from_tool_status():
    plan = InstallPlan(
        config=InstallConfig(),
        tools=[ToolInfo(name="klayout", status=ToolStatusEnum.WARNING)],
    )

    assert plan.has_warnings() is True
