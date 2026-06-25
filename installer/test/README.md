# Installer Test Suite

This directory contains the automated tests for the IHP-Open-PDK installer.

The suite is organized into three layers:

- `backend/` - fast unit tests for installer logic with no Qt widget dependency
- `frontend/` - PySide6 page and window tests using `pytest-qt`
- `integration/` - subprocess tests for `install.py`, non-GUI flows, and close behavior

Shared fixtures for most tests live in `installer/test/conftest.py`. The integration tests also define an `installer_worktree` fixture locally so they can run against a detached `installer` branch worktree.

## Quick Start

Recommended full-suite command:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
```

Direct pytest equivalent:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test -q
```

Run one layer:

```bash
./venv/bin/python -m pytest installer/test/backend -q
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/frontend -q
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/integration -q
```

## Prerequisites

Use the repository virtual environment:

- `./venv/bin/python`
- `./venv/bin/pip`

Python test dependencies:

- `pytest`
- `pytest-mock`
- `pytest-qt`

Install or refresh them with:

```bash
./venv/bin/pip install pytest pytest-mock pytest-qt
```

Additional host dependency:

- `git` - required by the integration suite because it creates a temporary detached worktree from the `installer` branch

GUI tests run headless. Set:

```bash
QT_QPA_PLATFORM=offscreen
```

## Current Layout

Test files:

- `installer/test/conftest.py`
- `installer/test/backend/test_checker.py`
- `installer/test/backend/test_cli_runner.py`
- `installer/test/backend/test_executor.py`
- `installer/test/backend/test_models.py`
- `installer/test/backend/test_pdk_registry.py`
- `installer/test/backend/test_tool_registry.py`
- `installer/test/frontend/test_check_page.py`
- `installer/test/frontend/test_choice_page.py`
- `installer/test/frontend/test_main_window_flow.py`
- `installer/test/integration/test_close_during_run.py`
- `installer/test/integration/test_install_cli.py`

Current count:

- backend: 73 tests
- frontend: 56 tests
- integration: 9 tests
- total: 138 tests

## File Coverage Map

### Backend

- `installer/test/backend/test_models.py`
  - `InstallConfig` defaults
  - normalized `PDK_ROOT` and `PDK` path behavior
  - duplicate-path protection
  - install plan helper behavior
- `installer/test/backend/test_checker.py`
  - tool discovery
  - version parsing and comparison
  - openvaf alias handling
  - `klayout-python` package detection and mismatch handling
  - local and GitHub source validation
  - environment checks, including install-destination override warnings
- `installer/test/backend/test_executor.py`
  - install-step generation
  - environment file writing
  - `.spiceinit` handling
  - command execution behavior
  - install log formatting
- `installer/test/backend/test_cli_runner.py`
  - `--eda-config` parsing
  - CLI config construction from parsed args
  - non-GUI override rejection behavior
- `installer/test/backend/test_pdk_registry.py`
  - PDK metadata for `ihp-sg13g2` and `ihp-sg13cmos5l`
  - dependency and default-branch expectations
- `installer/test/backend/test_tool_registry.py`
  - visible tool grouping by type
  - default tool-check candidates
  - display-name mapping

### Frontend

- `installer/test/frontend/test_choice_page.py`
  - configuration page defaults
  - PDK and source-mode switching
  - derived install-directory defaults
  - GitHub branch and commit UI state
  - EDA selection serialization
  - skip-tool-check behavior
- `installer/test/frontend/test_check_page.py`
  - tool selection visibility
  - default tool-check rows
  - recommended versions
  - table content, tooltips, and browse widgets
  - override confirmation behavior
  - `klayout-python` path inspection
- `installer/test/frontend/test_main_window_flow.py`
  - current 3-step flow
  - back/next button state changes
  - source-validation gating
  - skip-tool-check fast path
  - install success/failure reset behavior
  - override-confirmation flow

### Integration

- `installer/test/integration/test_install_cli.py`
  - `install.py --cli`
  - `install.py --test`
  - `install.py --nogui` change-mode flow
  - `--eda-config` replacement behavior
  - override rejection without `--allow-override`
- `installer/test/integration/test_close_during_run.py`
  - clean close from idle GUI state
  - clean close with a fake running executor
  - source-validation switching between local and GitHub modes

## Running Tests

The `--test` flag delegates to pytest.

- if no explicit pytest target is passed, it defaults to `installer/test/`
- if explicit test files or directories are passed, those targets are used directly

Examples:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test="-vv"
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test="-q" installer/test/backend/test_models.py
```

Run a layer:

```bash
./venv/bin/python -m pytest installer/test/backend -q
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/frontend -q
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/integration -q
```

Run one file:

```bash
./venv/bin/python -m pytest installer/test/backend/test_checker.py -q
```

Run a single test by name:

```bash
./venv/bin/python -m pytest installer/test/backend/test_checker.py -k override -q
```

Useful pytest flags:

```bash
./venv/bin/python -m pytest installer/test -vv
```

Stop on first failure:

```bash
./venv/bin/python -m pytest installer/test -x
```

Show print and log output:

```bash
./venv/bin/python -m pytest installer/test -s
```

## Suite Responsibilities

### Backend

Use backend tests first when the change can be validated from return values, object state, or generated plans.

- path normalization
- tool detection and version parsing
- source validation
- registry metadata
- install-step generation
- non-GUI CLI parsing and planning

### Frontend

Use frontend tests when the behavior lives in a Qt page or window and widget state matters.

- default widget selections
- checkbox and radio interactions
- button text and enabled state
- labels, tables, and tooltips
- page-to-page navigation state

### Integration

Use integration tests when the real `install.py` entrypoint, subprocess boundaries, or aggressive close behavior must be validated safely.

- delegated pytest behavior from `install.py --test`
- `--cli` and `--nogui` behavior
- override rejection at process level
- shutdown and close handling

## Shared Fixtures

`installer/test/conftest.py` provides shared setup for most backend and frontend tests.

### `fake_pdk_root`

Creates a synthetic PDK tree under `tmp_path`, including enough structure for installer logic such as:

- `libs.tech/ngspice/models`
- `libs.tech/ngspice/osdi`
- `libs.tech/xyce/models`
- `libs.tech/xyce/plugins`
- `libs.tech/gnucap`
- `libs.tech/klayout`
- `libs.tech/qucs-s`
- `libs.tech/xschem`
- `libs.tech/verilog-a/psp103`
- `libs.tech/verilog-a/r3_cmc`
- `libs.tech/verilog-a/mosvar`
- selected `libs.ref` directories

It also creates:

- a fake `.spiceinit`
- a fake `versions.txt` with expected tool-version lines

### `fake_home`

Creates a temporary home directory with a synthetic `.bashrc`.

### `mock_env`

Sets:

- `PDK_ROOT`
- `PDK`
- `HOME`
- `QT_QPA_PLATFORM=offscreen`

### `install_config`

Returns a fresh `InstallConfig` pointing at the fake PDK root.

### `app`

Provides the current Qt application instance.

### `theme_manager`

Creates a real `ThemeManager` in light mode for frontend tests.

## Integration-Local Fixtures and Helpers

The integration files define their own helpers because they execute real subprocesses from a temporary worktree.

- `installer_worktree`
  - creates a detached temporary worktree from the `installer` branch
  - removes the worktree after the test finishes
- `_base_env()`
  - preserves the current environment and sets `QT_QPA_PLATFORM=offscreen` if needed
- `_with_home()` in `test_install_cli.py`
  - overlays a temporary `HOME` directory for non-GUI install tests

## How To Add a New Test

### 1. Pick the Correct Layer

Use this rule of thumb:

- `backend/` - pure logic, registry data, planning, parsing, no widgets
- `frontend/` - page logic, widget state, signals, labels, tables, button state
- `integration/` - subprocesses, entrypoints, shutdown behavior, process-level validation

### 2. Prefer an Existing File

Examples:

- config and plan models -> `installer/test/backend/test_models.py`
- tool or environment checks -> `installer/test/backend/test_checker.py`
- executor behavior -> `installer/test/backend/test_executor.py`
- non-GUI arg parsing -> `installer/test/backend/test_cli_runner.py`
- PDK definitions -> `installer/test/backend/test_pdk_registry.py`
- tool registry defaults -> `installer/test/backend/test_tool_registry.py`
- configuration page behavior -> `installer/test/frontend/test_choice_page.py`
- tool and environment page behavior -> `installer/test/frontend/test_check_page.py`
- main flow and navigation -> `installer/test/frontend/test_main_window_flow.py`
- entrypoint and subprocess behavior -> `installer/test/integration/test_install_cli.py`

Create a new file only when an area becomes large enough to justify separation.

### 3. Name Tests Clearly

Use:

- file names: `test_<area>.py`
- test names: `test_<behavior>()`

Examples:

- `test_skip_tool_check_emits_signal`
- `test_install_nogui_rejects_override_without_flag`
- `test_tool_check_ids_include_openvaf_default_candidates`

### 4. Reuse Existing Fixtures

Before adding a new fixture, check whether one of these already solves the problem:

- `fake_pdk_root`
- `fake_home`
- `mock_env`
- `install_config`
- `theme_manager`
- `installer_worktree` for process-level integration coverage

Prefer extending shared fixtures only when many tests need the same new setup.

### 5. Keep Tests Small and Deterministic

- use `tmp_path` instead of real user paths
- monkeypatch external tools instead of depending on host-installed binaries when possible
- avoid real network usage
- keep subprocess tests bounded with timeouts
- assert behavior, not incidental implementation detail, when possible

### 6. Run the Smallest Relevant Subset First

Examples:

Changing `checker.py`:

```bash
./venv/bin/python -m pytest installer/test/backend/test_checker.py -q
```

Changing `check_page.py`:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/frontend/test_check_page.py -q
```

Changing `install.py`:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/integration/test_install_cli.py -q
```

Then run the full suite.

## Installer-Specific Pitfalls

### `install.py --test`

- default path `installer/test/` is only appended when no explicit target is passed
- explicit test files and directories must remain explicit

### `install.py --nogui`

- non-GUI tests cover real CLI install flows, not just argument parsing
- override-sensitive destinations must fail without `--allow-override`

### Hidden Simulator Dependencies

These are not part of the visible tool checklist:

- `openvaf/openvaf-r`
- `buildxyceplugin`
- `gnucap-mg-vams`

Tests should validate them through configured-tool behavior, not visible checkbox presence.

### `klayout-python`

- it appears in tool results, not in the visible tool-selection list
- mismatch behavior compares the KLayout binary version and Python package version

### Destructive Close Behavior

`MainWindow.closeEvent()` is intentionally aggressive and may call `os._exit(0)`.

- do not test real destructive close behavior in ordinary widget tests
- use subprocess-based integration tests instead

### Worktree Requirement

Integration tests assume:

- the repository is available as a git checkout
- the `installer` branch exists locally
- `git worktree` can create a detached worktree for subprocess execution

### GUI Style Tests

Do not write brittle pixel-perfect UI tests.

Prefer assertions on:

- labels
- object names
- visible or hidden state
- enabled or disabled state
- table headers
- cell values
- tooltips

## Current Baseline

Known-good baseline command:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
```

Expected result at the time of writing:

- `138 passed`

Use that as the baseline check after modifying installer code or tests.
