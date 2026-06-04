from dataclasses import dataclass


@dataclass(frozen=True)
class PDKDefinition:
    id: str
    label: str
    family: str
    kind: str
    repo_url: str
    allowed_branches: tuple[str, ...]
    default_branch: str
    dependencies: tuple[str, ...]
    repo_layout: str
    required_dirs: tuple[str, ...]
    supported_tools: tuple[str, ...]


PDK_DEFINITIONS: tuple[PDKDefinition, ...] = (
    PDKDefinition(
        id="ihp-sg13g2",
        label="SG13G2",
        family="sg13",
        kind="base",
        repo_url="https://github.com/IHP-GmbH/IHP-Open-PDK.git",
        allowed_branches=("dev", "main"),
        default_branch="dev",
        dependencies=(),
        repo_layout="repo_root_contains_pdk_dir",
        required_dirs=("libs.tech", "libs.ref"),
        supported_tools=(
            "ngspice",
            "Xyce",
            "gnucap",
            "xschem",
            "qucs-s",
            "klayout",
        ),
    ),
    PDKDefinition(
        id="ihp-sg13cmos5l",
        label="SG13CMOS5L",
        family="sg13",
        kind="derived",
        repo_url="https://github.com/IHP-GmbH/ihp-sg13cmos5l.git",
        allowed_branches=("main",),
        default_branch="main",
        dependencies=("ihp-sg13g2",),
        repo_layout="detect",
        required_dirs=("libs.tech", "libs.ref"),
        supported_tools=(
            "ngspice",
            "Xyce",
            "gnucap",
            "xschem",
            "qucs-s",
            "klayout",
        ),
    ),
)


PDK_DEFINITION_MAP = {pdk.id: pdk for pdk in PDK_DEFINITIONS}


def get_pdk_definition(pdk_id: str) -> PDKDefinition:
    return PDK_DEFINITION_MAP[pdk_id]
