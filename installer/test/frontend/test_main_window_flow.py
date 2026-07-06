from installer.frontend.main_window import MainWindow


def _safe_close_event(self, event):
    event.accept()


def setup_module(module):
    MainWindow.closeEvent = _safe_close_event


def _make_window(qtbot, theme_manager):
    window = MainWindow(theme_manager)
    qtbot.addWidget(window)
    window.show()
    return window


def test_initial_state_has_configuration_header_and_hidden_back(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window.current_step == 0
    assert window.header_label.text() == "Configuration"
    assert window.step_label.text() == "Step 1 of 2: Configuration"
    assert window.back_btn.isHidden() is True
    assert window.tool_check_btn.isHidden() is False
    assert window.close_btn.isHidden() is False


def test_env_vars_auto_select_change_mode(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window.choice_page.mode_change.isChecked() is True
    assert window.choice_page.mode_new.isChecked() is False


def test_invalid_local_source_disables_next(qtbot, theme_manager, mock_env, monkeypatch):
    monkeypatch.setattr("installer.frontend.main_window.validate_local_source", lambda cfg: (False, "bad local source"))
    window = _make_window(qtbot, theme_manager)

    window.choice_page.local_source_input.setText("/tmp/invalid")
    window._refresh_source_validity()

    assert window.next_btn.isEnabled() is False


def test_switching_to_github_lifts_local_disable_when_github_valid(qtbot, theme_manager, mock_env, monkeypatch):
    monkeypatch.setattr("installer.frontend.main_window.validate_local_source", lambda cfg: (False, "bad local source"))
    monkeypatch.setattr("installer.frontend.main_window.validate_github_source", lambda cfg: (True, ""))
    window = _make_window(qtbot, theme_manager)

    window.choice_page.local_source_input.setText("/tmp/invalid")
    window._refresh_source_validity()
    assert window.next_btn.isEnabled() is False

    window.choice_page.source_github.click()
    window._refresh_source_validity()

    assert window.next_btn.isEnabled() is True


def test_invalid_github_source_disables_next(qtbot, theme_manager, mock_env, monkeypatch):
    monkeypatch.setattr("installer.frontend.main_window.validate_github_source", lambda cfg: (False, "use local"))
    window = _make_window(qtbot, theme_manager)

    window.choice_page.source_github.click()
    window._refresh_source_validity()

    assert window.next_btn.isEnabled() is False


def test_commit_prefix_shorter_than_min_disables_next_without_remote_validation(qtbot, theme_manager, mock_env, monkeypatch):
    calls = {"count": 0}

    def fake_validate(cfg):
        calls["count"] += 1
        return True, ""

    monkeypatch.setattr("installer.frontend.main_window.validate_github_source", fake_validate)
    window = _make_window(qtbot, theme_manager)

    window.choice_page.source_github.click()
    window.choice_page.github_commit_radio.click()
    count_before_short_input = calls["count"]
    window.choice_page.github_commit_input.setText("abc123")
    window._refresh_source_validity()

    assert window.next_btn.isEnabled() is False
    assert "at least 7 characters" in window.choice_page.source_status.text()
    assert calls["count"] == count_before_short_input


def test_valid_historical_commit_prefix_reenables_next_after_background_validation(qtbot, theme_manager, mock_env, monkeypatch):
    def fake_validate(cfg):
        cfg.resolved_github_commit = "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
        return True, ""

    monkeypatch.setattr("installer.frontend.main_window.validate_github_source", fake_validate)
    window = _make_window(qtbot, theme_manager)
    window._github_validation_timer.setInterval(0)

    window.choice_page.source_github.click()
    window.choice_page.github_commit_radio.click()
    window.choice_page.github_commit_input.setText("deadbee")

    assert window.next_btn.isEnabled() is False

    qtbot.waitUntil(lambda: window.next_btn.isEnabled(), timeout=2000)

    assert window.config.resolved_github_commit == "deadbeefdeadbeefdeadbeefdeadbeefdeadbeef"
    assert window.choice_page.source_status.isHidden() is True


def test_switching_back_to_valid_local_reenables_next(qtbot, theme_manager, mock_env, monkeypatch):
    monkeypatch.setattr("installer.frontend.main_window.validate_github_source", lambda cfg: (False, "use local"))
    monkeypatch.setattr("installer.frontend.main_window.validate_local_source", lambda cfg: (True, ""))
    window = _make_window(qtbot, theme_manager)

    window.choice_page.source_github.click()
    window._refresh_source_validity()
    assert window.next_btn.isEnabled() is False

    window.choice_page.source_local.click()
    window._refresh_source_validity()

    assert window.next_btn.isEnabled() is True


def test_open_tool_check_window_creates_separate_window(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    window.tool_check_btn.click()

    assert window.tool_check_window is not None
    assert window.tool_check_window.isVisible() is True
    assert window.tool_check_window.check_page.tc_section.isVisible() is True


def test_tool_check_window_back_returns_to_tool_selection(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    window.tool_check_btn.click()
    tool_window = window.tool_check_window
    tool_window.check_page.show_tool_selection()
    tool_window.check_page.tc_checks["openvaf/openvaf-r"].setChecked(False)
    tool_window.check_page.tc_checks["python3"].setChecked(True)
    tool_window.check_page._on_tool_done([])

    assert tool_window.back_btn.isHidden() is False
    assert tool_window.check_btn.isHidden() is True

    tool_window.back_btn.click()

    assert tool_window.check_page._tc_phase == "selection"
    assert tool_window.check_page.tc_section.isVisible() is True
    assert tool_window.check_page.tc_checks["openvaf/openvaf-r"].isChecked() is False
    assert tool_window.check_page.tc_checks["python3"].isChecked() is True
    assert tool_window.back_btn.isHidden() is True
    assert tool_window.check_btn.isHidden() is False


def test_next_is_disabled_while_tool_check_window_is_open_and_reenabled_on_close(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window.next_btn.isEnabled() is True

    window.tool_check_btn.click()

    assert window.next_btn.isEnabled() is False
    assert window.current_step == 0

    window.tool_check_window.close()
    qtbot.waitUntil(lambda: window.tool_check_window is None, timeout=1000)

    assert window.next_btn.isEnabled() is True


def test_next_from_step0_goes_directly_to_install(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))

    window._on_next_action()

    assert called == [1]


def test_go_to_install_step_calls_env_and_install(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = {"env": False}

    monkeypatch.setattr(window.check_page, "start_env_and_install", lambda: called.__setitem__("env", True))

    window._go_to_step(1)

    assert window.current_step == 1
    assert window.tool_check_btn.isHidden() is True
    assert window.next_btn.isHidden() is True
    assert called["env"] is True


def test_nav_state_install_text_sets_install_style(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 1
    window.next_btn.show()

    window._on_nav_state_changed({"next_enabled": True, "next_text": "Install", "back_enabled": True})

    assert window.next_btn.text() == "Install"
    assert window.next_btn.objectName() == "install_btn"
    assert window.next_btn.isHidden() is False
    assert window.back_btn.isEnabled() is True


def test_step_names_are_current_two_step_flow(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window._step_name(0) == "Configuration"
    assert window._step_name(1) == "Install"


def test_install_step_cancelled_by_override_confirmation_does_not_start(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 1
    called = {"install": False}

    monkeypatch.setattr(window.check_page, "confirm_install_if_needed", lambda: False)
    monkeypatch.setattr(window.check_page, "start_install", lambda: called.__setitem__("install", True))

    window._on_next_action()

    assert called["install"] is False


def test_install_step_confirmed_by_override_confirmation_starts(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 1
    called = {"install": False}

    monkeypatch.setattr(window.check_page, "confirm_install_if_needed", lambda: True)
    monkeypatch.setattr(window.check_page, "start_install", lambda: called.__setitem__("install", True))

    window._on_next_action()

    assert called["install"] is True


def test_back_from_success_resets_to_defaults_and_returns_to_configuration(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 1
    window.choice_page.mode_change.setChecked(True)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window._on_install_finished(True)

    assert window.back_btn.text() == "Start"

    window._on_back()

    assert called == [0]
    assert window.choice_page.mode_new.isChecked() is True
    assert window._install_finished is False
    assert window._install_succeeded is False


def test_back_from_failure_preserves_values_and_returns_to_configuration(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 1
    window.choice_page.mode_change.setChecked(True)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window._on_install_finished(False)

    assert window.back_btn.text() == "< Back"

    window._on_back()

    assert called == [0]
    assert window.choice_page.mode_change.isChecked() is True
