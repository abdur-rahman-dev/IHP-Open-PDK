from installer.backend.models import InstallConfig, InstallPlan, PDKChoice, ToolInfo, ToolStatusEnum


def test_install_config_defaults():
    cfg = InstallConfig()

    assert cfg.pdk == PDKChoice.SG13G2
    assert cfg.compile_verilog_a is True
    assert cfg.skip_tool_check is False
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
