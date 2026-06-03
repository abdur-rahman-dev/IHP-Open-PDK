# Installer Test Suite

This directory contains automated tests for the IHP-Open-PDK installer.

The tests are split into three layers:

- `backend/` - fast unit tests for installer logic with no Qt dependency
- `frontend/` - PySide6 widget/page tests using `pytest-qt`
- `integration/` - higher-level subprocess tests for `install.py` and close behavior

The shared fixtures for all suites live in `installer/test/conftest.py`.

## Quick Start

Run the full suite:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
```

Run backend only:

```bash
./venv/bin/python -m pytest installer/test/backend -q
```

Run frontend only:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/frontend -q
```

Run integration only:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/integration -q
```

## Prerequisites

Use the repository virtual environment:

- `./venv/bin/python`
- `./venv/bin/pip`

Required packages:

- `pytest`
- `pytest-mock`
- `pytest-qt`

Install or refresh them with:

```bash
./venv/bin/pip install pytest pytest-mock pytest-qt
```

GUI tests run headless. Set:

```bash
QT_QPA_PLATFORM=offscreen
```

## Directory Layout

Current layout:

- `installer/test/conftest.py`
- `installer/test/backend/test_models.py`
- `installer/test/backend/test_checker.py`
- `installer/test/backend/test_executor.py`
- `installer/test/frontend/test_choice_page.py`
- `installer/test/frontend/test_check_page.py`
- `installer/test/frontend/test_main_window_flow.py`
- `installer/test/integration/test_install_cli.py`
- `installer/test/integration/test_close_during_run.py`

What each file covers:

- `test_models.py`
  - `InstallConfig` defaults
  - normalized source/target PDK path behavior
  - duplicate path regression protection
  - plan error/warning helpers
- `test_checker.py`
  - tool discovery
  - version parsing
  - openvaf alias handling
  - env checks
  - `klayout-python` package and mismatch behavior
- `test_executor.py`
  - install step generation
  - env writing
  - `.spiceinit` handling
  - command execution behavior
  - install log step separators
- `test_choice_page.py`
  - configuration page defaults
  - PDK/mode toggles
  - config serialization
- `test_check_page.py`
  - tool check page behavior
  - environment report behavior
  - custom path handling
  - recommended versions and table contents
- `test_main_window_flow.py`
  - 3-step flow
  - nav state changes
  - skip-tool-check flow
- `test_install_cli.py`
  - `install.py --cli`
  - `install.py --test`
- `test_close_during_run.py`
  - subprocess-based close behavior checks

## Running Tests

### Full Suite Through Installer Entrypoint

This is the recommended top-level command:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
```

The `--test` flag delegates to pytest.

- If no explicit pytest target is passed, it defaults to `installer/test/`
- If explicit test files or directories are passed, those targets are used directly

Examples:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test="-vv"
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test="-q" installer/test/backend/test_models.py
```

### Full Suite Directly With Pytest

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test -q
```

### Backend Suite

```bash
./venv/bin/python -m pytest installer/test/backend -q
```

Use backend tests when changing:

- `installer/backend/models.py`
- `installer/backend/checker.py`
- `installer/backend/executor.py`

### Frontend Suite

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/frontend -q
```

Use frontend tests when changing:

- `installer/frontend/choice_page.py`
- `installer/frontend/check_page.py`
- `installer/frontend/main_window.py`
- `installer/frontend/theme.py` behavior that affects widget state or test setup

### Integration Suite

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/integration -q
```

Use integration tests when changing:

- `install.py`
- process-level close behavior
- CLI/output behavior
- subprocess startup/shutdown flows

### Run One File

```bash
./venv/bin/python -m pytest installer/test/backend/test_models.py -q
```

### Run a Single Test by Name

```bash
./venv/bin/python -m pytest installer/test/backend/test_models.py -k target_name -q
```

### Useful Pytest Flags

- verbose output:

```bash
./venv/bin/python -m pytest installer/test -vv
```

- stop on first failure:

```bash
./venv/bin/python -m pytest installer/test -x
```

- show print/log output:

```bash
./venv/bin/python -m pytest installer/test -s
```

## Suite Responsibilities

### Backend

Backend tests should be the first place to add coverage when the change does not require Qt widgets.

Backend tests are expected to cover:

- normalized `PDK_ROOT` and `PDK` path behavior
- tool detection and version parsing
- openvaf alias handling
- `klayout-python` detection and mismatch logic
- environment check generation
- install step generation and executor behavior

Choose the backend suite when:

- the logic can be tested from return values or object state
- no widget, signal loop, or visual state is involved

### Frontend

Frontend tests cover page logic and widget state with `pytest-qt`.

Frontend tests are expected to cover:

- default widget selections
- checkbox/radio interactions
- button text and enabled state
- table content and tooltips
- nav state transitions
- page-level helper behavior

Choose the frontend suite when:

- the behavior lives in a Qt page, dialog, or window
- signals, labels, tables, or button state matter
- subprocess boundaries do not need to be tested

### Integration

Integration tests validate public behavior from subprocess boundaries.

Integration tests are expected to cover:

- CLI entrypoint behavior
- delegated pytest behavior from `install.py --test`
- close behavior that would be unsafe to test directly inside normal widget tests

Choose the integration suite when:

- the real entrypoint matters
- a subprocess is the safest way to validate behavior
- shutdown/process management is part of the bug or feature

## Shared Fixtures

`installer/test/conftest.py` currently provides shared setup for the suites.

### `fake_pdk_root`

Creates a synthetic PDK tree under `tmp_path`, including enough structure for installer logic such as:

- `libs.tech/ngspice`
- `libs.tech/xyce`
- `libs.tech/gnucap`
- `libs.tech/klayout`
- `libs.tech/qucs-s`
- `libs.tech/verilog-a`
- selected `libs.ref` directories

It also creates:

- a fake `.spiceinit`
- a fake `versions.txt`

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

## How To Add a New Test

### 1. Pick the Correct Suite

Use this rule of thumb:

- `backend/`
  - pure logic
  - no Qt widgets needed
- `frontend/`
  - widget or page logic
  - signals, labels, button states, table behavior
- `integration/`
  - subprocesses
  - entrypoints
  - close/process/shutdown behavior

### 2. Choose the Right File

Prefer extending an existing file when the behavior fits naturally.

Examples:

- path normalization -> `test_models.py`
- tool/env detection -> `test_checker.py`
- install-step logic -> `test_executor.py`
- config page behavior -> `test_choice_page.py`
- tool/env page behavior -> `test_check_page.py`
- nav flow -> `test_main_window_flow.py`
- `install.py` behavior -> `test_install_cli.py`

Create a new file only when an area becomes large enough to justify separation.

### 3. Name Tests Clearly

Use:

- file names: `test_<area>.py`
- test names: `test_<behavior>()`

Examples:

- `test_skip_tool_check_emits_signal`
- `test_check_tools_klayout_python_mismatch`
- `test_install_test_delegates_to_pytest`

### 4. Reuse Existing Fixtures

Before adding a new fixture, check whether one of these already solves the problem:

- `fake_pdk_root`
- `fake_home`
- `mock_env`
- `install_config`
- `theme_manager`

Prefer extending shared fixtures only when many tests need the same new setup.

### 5. Keep Tests Small and Deterministic

- use `tmp_path` instead of real user paths
- monkeypatch external tools instead of depending on host-installed binaries when possible
- avoid real network usage
- keep subprocess tests bounded with timeouts
- assert behavior, not incidental implementation detail, when possible

### 6. Run the Smallest Relevant Subset First

Examples:

- changing `checker.py`:

```bash
./venv/bin/python -m pytest installer/test/backend/test_checker.py -q
```

- changing `check_page.py`:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/frontend/test_check_page.py -q
```

- changing `install.py`:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python -m pytest installer/test/integration/test_install_cli.py -q
```

Then run the full suite.

## How To Add a New Test Suite

Only add a new suite if it has a clearly distinct purpose and will contain multiple related tests.

If needed:

1. create a new subdirectory under `installer/test/`
2. add `__init__.py`
3. document the suite in this README
4. add example commands for running it
5. explain why it is separate from backend/frontend/integration

Do not create a new suite for a single isolated test file.

## Installer-Specific Pitfalls

### `install.py --test`

- default path `installer/test/` is only appended when no explicit target is passed
- explicit test files/directories must remain explicit

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

- do not test real destructive close behavior in ordinary frontend widget tests
- use subprocess-based integration tests instead

### GUI Style Tests

Do not write brittle pixel-perfect UI tests.

Prefer assertions on:

- labels
- object names
- visible/hidden state
- enabled/disabled state
- table headers
- cell values
- tooltips

### Branch Context Matters

These tests belong to the `installer` branch. Running them from a branch where installer files are absent or untracked may fail or give misleading results.

## Current Baseline

Known-good baseline at the time of writing:

```bash
QT_QPA_PLATFORM=offscreen ./venv/bin/python install.py --test=-q
```

Expected result:

- `69 passed`

Use that as the baseline check after modifying installer code or tests.
