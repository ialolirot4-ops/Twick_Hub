from twick_hub.presentation.qml_bridge.theme import Theme


def test_starts_in_dark_mode(qapp):
    theme = Theme()
    assert theme.darkMode is True
    assert theme.background == "#14161B"


def test_toggle_switches_and_updates_derived_colors(qapp):
    theme = Theme()
    theme.toggle()
    assert theme.darkMode is False
    assert theme.background == "#F7F6F3"
    theme.toggle()
    assert theme.darkMode is True


def test_toggle_emits_change_signal_exactly_once(qapp):
    theme = Theme()
    seen = []
    theme.darkModeChanged.connect(lambda: seen.append(theme.darkMode))
    theme.toggle()
    assert seen == [False]


def test_setting_same_value_does_not_emit(qapp):
    theme = Theme()
    seen = []
    theme.darkModeChanged.connect(lambda: seen.append(True))
    # PySide6's stub doesn't model the setter for a Property declared in
    # the functional (getter, setter) form as assignable — real Qt/QML
    # code assigns to it directly and it works (verified); the ignore is
    # scoped to this one known stub gap, not the surrounding logic.
    theme.darkMode = True  # pyright: ignore[reportAttributeAccessIssue]
    assert seen == []


def test_twitch_and_kick_badge_colors_are_fixed_regardless_of_theme(qapp):
    """These never move with dark/light — see theme.py's module docstring:
    they're the only place platform brand colors appear at all."""
    theme = Theme()
    twitch, kick = theme.twitchBadge, theme.kickBadge
    theme.toggle()
    assert theme.twitchBadge == twitch
    assert theme.kickBadge == kick
