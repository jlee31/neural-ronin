"""
Gymnasium wrapper around the headless neural-ronin Game.

Run from project root:
    python -m rl.train

The wrapper reuses a single Game instance for the env lifetime — pygpen's
`init()` builds singletons (Window, EntityDB, etc.) that can't be safely
re-created in-process. `Game.reset()` is the per-episode reset.
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from main import Game, STATE_GAME_OVER
from scripts.player import (
    MAX_HEALTH, RUN_SPEED, MAX_FALL, ATTACK_COOLDOWN, INVULN_TIME, DASH_COOLDOWN,
)
from scripts.SETTINGS import DISPLAY_WIDTH, DISPLAY_HEIGHT

# Discrete action set. Multi-key combos cover what a human actually plays:
# moving while jumping, attacking on the move. Left+right is excluded
# (cancels in the player update).
ACTIONS = [
    {},
    {"left": True},
    {"right": True},
    {"jump": True},
    {"attack": True},
    {"left": True, "jump": True},
    {"right": True, "jump": True},
    {"left": True, "attack": True},
    {"right": True, "attack": True},
    {"dash": True},
    {"left": True, "dash": True},
    {"right": True, "dash": True},
]

MAX_EPISODE_STEPS = 60 * 60  # 60 seconds of sim time at 60Hz
OBS_DIM = 17

# pygpen's singleton registry is process-global and silently overwritten by each
# Game() — a second in-process env would cross-wire the first env's entities to
# the wrong Game. Fail loudly instead; use SubprocVecEnv for parallel envs.
_env_created = False


class GameEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, seed=None):
        super().__init__()
        global _env_created
        if _env_created:
            raise RuntimeError(
                "Only one GameEnv per process (pygpen singletons are process-global). "
                "Use SubprocVecEnv, not DummyVecEnv/make_vec_env, for parallel envs."
            )
        _env_created = True
        self.action_space = spaces.Discrete(len(ACTIONS))
        # All features are pre-normalized to roughly [-1, 1]. Use a slightly
        # wider Box so a brief velocity overshoot doesn't trip SB3's checks.
        self.observation_space = spaces.Box(
            low=-2.0, high=2.0, shape=(OBS_DIM,), dtype=np.float32
        )

        self.game = Game(headless=True, seed=seed)
        self.game.load()

        self._prev_score = 0
        self._prev_health = MAX_HEALTH
        # alive-enemy HP total after the previous step — only game.step() mutates
        # it, so caching saves a full enemy scan at the top of every step
        self._prev_enemy_health = 0
        self._steps = 0

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        self.game.reset(seed=seed)
        self._prev_score = self.game.score
        self._prev_health = self.game.player.health
        self._prev_enemy_health = sum(e.health for e in self.game.enemies if e.alive)
        self._steps = 0
        return self._get_obs(), {}

    def step(self, action):
        enemy_health_before = self._prev_enemy_health

        self.game.step(ACTIONS[int(action)])
        self._steps += 1

        score_delta = self.game.score - self._prev_score
        health_delta = self.game.player.health - self._prev_health
        self._prev_score = self.game.score
        self._prev_health = self.game.player.health

        # Dense damage-dealt signal: how much enemy HP disappeared this tick.
        # max(0) so enemy respawns (HP goes up) don't give negative reward.
        enemy_health_after = sum(e.health for e in self.game.enemies if e.alive)
        self._prev_enemy_health = enemy_health_after
        damage_dealt = max(0, enemy_health_before - enemy_health_after)

        terminated = self.game.state == STATE_GAME_OVER
        truncated = self._steps >= MAX_EPISODE_STEPS

        reward = (
            1.5 * damage_dealt                  # reward every hit, not just kills
            + 0.03 * score_delta                # small kill bonus on top
            - 1.0 * max(0, -health_delta)       # penalty for taking a hit
            - 0.001                             # time-step cost
        )
        if terminated:
            reward -= 5.0

        return self._get_obs(), float(reward), terminated, truncated, {
            "score": self.game.score,
            "level": self.game.level,
            "health": self.game.player.health,
        }

    def _get_obs(self):
        return build_obs(self.game)

    def close(self):
        pass


def _scan_enemies(game):
    """One pass over game.enemies: nearest living enemy (by x) + dead count."""
    px = game.player.center[0]
    nearest = None
    best = float("inf")
    dead = 0
    for enemy in game.enemies:
        if not enemy.alive:
            dead += 1
            continue
        d = abs(enemy.center[0] - px)
        if d < best:
            best = d
            nearest = enemy
    return nearest, dead


def build_obs(game):
    """Module-level so both the headless env and the rendered watch loop can call it."""
    p = game.player
    enemy, dead_count = _scan_enemies(game)

    if enemy is not None:
        dx = (enemy.center[0] - p.center[0]) / DISPLAY_WIDTH
        dy = (enemy.center[1] - p.center[1]) / DISPLAY_HEIGHT
        enemy_alive = 1.0
        enemy_attacking = 1.0 if enemy.attacking else 0.0
        # How close is the enemy to being able to swing again? 0 = ready, 1 = just attacked.
        enemy_cd_frac = np.clip(enemy.melee_cd / max(enemy.melee_cooldown_base, 1e-6), 0.0, 1.0)
    else:
        dx = dy = 0.0
        enemy_alive = 0.0
        enemy_attacking = 0.0
        enemy_cd_frac = 0.0

    # Fraction of the level cleared: whole waves done + dead share of the current one.
    dead_frac = dead_count / max(1, len(game.enemies))
    level_progress = ((game.wave - 1) + dead_frac) / max(1, game.level_cfg["wave_count"])

    return np.array([
        p.center[0] / game.map_w,
        p.center[1] / game.map_h,
        np.clip(p.velocity[0] / RUN_SPEED, -2.0, 2.0),
        np.clip(p.velocity[1] / MAX_FALL, -2.0, 2.0),
        p.health / MAX_HEALTH,
        1.0 if p.air_time > 0.08 else 0.0,
        1.0 if p.attacking else 0.0,
        np.clip(p.attack_cd / ATTACK_COOLDOWN, 0.0, 1.0),   # can I swing right now?
        np.clip(p.invuln / INVULN_TIME, 0.0, 1.0),           # am I in i-frames?
        1.0 if p.dashing else 0.0,                            # am I mid-dodge?
        np.clip(p.dash_cd / DASH_COOLDOWN, 0.0, 1.0),        # can I dash right now?
        np.clip(dx, -2.0, 2.0),
        np.clip(dy, -2.0, 2.0),
        enemy_alive,
        enemy_attacking,
        enemy_cd_frac,                                         # is enemy about to swing?
        np.clip(level_progress, 0.0, 1.0),                    # how close to level-up?
    ], dtype=np.float32)
