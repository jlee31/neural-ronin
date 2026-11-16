"""
Entities read input through one of these instead of pygame directly.
PygameInputSource wraps pygpen's Input for live play; ScriptedInputSource
is driven by a dict each tick for headless mode.
"""


class PygameInputSource:
    def __init__(self, pp_input):
        self._inp = pp_input

    def pressed(self, key):
        return self._inp.pressed(key)

    def holding(self, key):
        return self._inp.holding(key)

    def clear(self):
        pass


class ScriptedInputSource:
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
        for key in self._held:
            self._held[key] = False
            self._just_pressed[key] = False
