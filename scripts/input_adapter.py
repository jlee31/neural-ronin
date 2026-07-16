"""
Input source for entity code.

Player and enemies should NOT read from pygame directly. They read from an
InputSource — either PygameInputSource (wraps pygpen's Input) for live play, or
ScriptedInputSource (dict-driven) for headless RL training. Same `pressed` /
`holding` API as pygpen's Input so call sites don't care.
"""


class PygameInputSource:
    """Live mode: forward calls to pygpen's Input singleton."""

    def __init__(self, pp_input):
        self._inp = pp_input

    def pressed(self, key):
        return self._inp.pressed(key)

    def holding(self, key):
        return self._inp.holding(key)

    def clear(self):
        pass  # pygpen's Input owns real keyboard state; nothing to reset


class ScriptedInputSource:
    """
    Headless mode: actions set by the RL env each step.

    `set_actions({"left": True, "jump": False, ...})` replaces the held state.
    `pressed` fires for one step when a key transitions from not-held to held.
    """

    def __init__(self, keys):
        self._held = {k: False for k in keys}
        self._just_pressed = {k: False for k in keys}

    def set_actions(self, actions):
        for key in self._held:
            now_held = bool(actions.get(key, False))
            self._just_pressed[key] = now_held and not self._held[key]
            self._held[key] = now_held

    def pressed(self, key):
        return self._just_pressed.get(key, False)

    def holding(self, key):
        return self._held.get(key, False)

    def clear(self):
        """Forget held state between episodes — a key held across a reset must
        register as a fresh press, or the first post-reset action is swallowed."""
        for key in self._held:
            self._held[key] = False
            self._just_pressed[key] = False
