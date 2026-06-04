from installer.backend.pdk_registry import get_pdk_definition


def test_sg13g2_definition_metadata():
    pdk = get_pdk_definition("ihp-sg13g2")

    assert pdk.family == "sg13"
    assert pdk.kind == "base"
    assert pdk.default_branch == "dev"
    assert pdk.dependencies == ()
    assert "ngspice" in pdk.supported_tools


def test_sg13cmos5l_definition_metadata():
    pdk = get_pdk_definition("ihp-sg13cmos5l")

    assert pdk.family == "sg13"
    assert pdk.kind == "derived"
    assert pdk.default_branch == "main"
    assert pdk.dependencies == ("ihp-sg13g2",)
    assert "klayout" in pdk.supported_tools
