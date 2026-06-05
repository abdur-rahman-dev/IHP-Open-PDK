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
    assert window.step_label.text() == "Step 1 of 3: Configuration"
    assert window.back_btn.isHidden() is True
    assert window.close_btn.isHidden() is False


def test_env_vars_auto_select_change_mode(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window.choice_page.mode_change.isChecked() is True
    assert window.choice_page.mode_new.isChecked() is False


def test_step0_next_text_normal_and_skip_toggle(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window.next_btn.text() == "Next >"

    window.choice_page.skip_tool_check_cb.click()

    assert window.next_btn.text() == "Next >"
    assert window.next_btn.objectName() == ""


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


def test_go_to_step_one_updates_buttons_and_calls_show_tool_selection(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = {"show": False}

    monkeypatch.setattr(window.check_page, "show_tool_selection", lambda: called.__setitem__("show", True))

    window._go_to_step(1)

    assert window.current_step == 1
    assert window.back_btn.isEnabled() is True
    assert window.next_btn.text() == "Next >"
    assert window.next_btn.isEnabled() is False
    assert called["show"] is True


def test_go_to_step_two_calls_env_and_install(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = {"env": False}

    monkeypatch.setattr(window.check_page, "start_env_and_install", lambda: called.__setitem__("env", True))

    window._go_to_step(2)

    assert window.current_step == 2
    assert window.back_btn.isEnabled() is False
    assert window.next_btn.isHidden() is True
    assert called["env"] is True


def test_skip_tool_check_jumps_directly_to_install(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window.choice_page.skip_tool_check_cb.setChecked(True)

    window._on_next_action()

    assert called == [2]


def test_normal_next_from_step0_goes_to_tool_check(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window.choice_page.skip_tool_check_cb.setChecked(False)

    window._on_next_action()

    assert called == [1]


def test_empty_eda_selection_does_not_block_progress(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    for cb in window.choice_page.sim_checks.values():
        cb.setChecked(False)
    for cb in window.choice_page.sch_checks.values():
        cb.setChecked(False)
    for cb in window.choice_page.lay_checks.values():
        cb.setChecked(False)

    window._on_next_action()

    assert called == [1]


def test_back_navigation(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window.current_step = 1
    window._on_back()
    window.current_step = 2
    window._on_back()

    assert called == [0, 1]


def test_install_success_enables_start_and_resets_to_defaults(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 2
    window.choice_page.mode_change.setChecked(True)
    window.choice_page.skip_tool_check_cb.setChecked(True)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window._on_install_finished(True)

    assert window.back_btn.isEnabled() is True
    assert window.back_btn.text() == "Start"

    window._on_back()

    assert called == [0]
    assert window.choice_page.mode_new.isChecked() is True
    assert window.choice_page.skip_tool_check_cb.isChecked() is False


def test_install_failure_enables_back_and_preserves_values(qtbot, theme_manager, mock_env, monkeypatch):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 2
    window.choice_page.mode_change.setChecked(True)
    window.choice_page.skip_tool_check_cb.setChecked(True)
    called = []

    monkeypatch.setattr(window, "_go_to_step", lambda step: called.append(step))
    window._on_install_finished(False)

    assert window.back_btn.isEnabled() is True
    assert window.back_btn.text() == "< Back"

    window._on_back()

    assert called == [0]
    assert window.choice_page.mode_change.isChecked() is True
    assert window.choice_page.skip_tool_check_cb.isChecked() is True


def test_nav_state_changed_updates_buttons(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 1

    window._on_nav_state_changed({"next_enabled": True, "next_text": "Next >", "back_enabled": False})

    assert window.next_btn.isEnabled() is True
    assert window.next_btn.text() == "Next >"
    assert window.back_btn.isEnabled() is False


def test_nav_state_install_text_sets_install_style(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)
    window.current_step = 2
    window.next_btn.show()

    window._on_nav_state_changed({"next_enabled": True, "next_text": "Install", "back_enabled": True})

    assert window.next_btn.text() == "Install"
    assert window.next_btn.objectName() == "install_btn"
    assert window.next_btn.isHidden() is False
    assert window.back_btn.isEnabled() is True


def test_step_names_are_current_three_step_flow(qtbot, theme_manager, mock_env):
    window = _make_window(qtbot, theme_manager)

    assert window._step_name(0) == "Configuration"
    assert window._step_name(1) == "Tool Requirements Check"
    assert window._step_name(2) == "Install"
