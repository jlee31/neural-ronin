"""
Gymnasium wrapper around the headless Game.

One Game per env for the env's lifetime; pygpen's init() builds process-wide
singletons, so a second GameEnv in the same process raises. Use SubprocVecEnv
for parallel envs.
"""

import numpy as np
import gymnasium as gym
from gymnasium import spaces

from main import Game, STATE_GAME_OVER
from scripts.player import (
    MAX_HEALTH, RUN_SPEED, MAX_FALL, ATTACK_COOLDOWN, INVULN_TIME, DASH_COOLDOWN,
)
from scripts.SETTINGS import DISPLAY_WIDTH, DISPLAY_HEIGHT

# buttons held for one tick; left+right is left out since they cancel
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

MAX_EPISODE_STEPS = 60 * 60  # 60 sim seconds
OBS_DIM = 17

_env_created = False


class GameEnv(gym.Env):
    metadata = {"render_modes": []}

    def __init__(self, seed=None):
        super().__init__()
        global _env_created
        if _env_created:
            raise RuntimeError(
                "Only one GameEnv per process (pygpen singletons are process-global). "
                "Use SubprocVecEnv for parallel envs."
            )
        _env_created = True
        self.action_space = spaces.Discrete(len(ACTIONS))
        # features are roughly in [-1, 1]; wider box so velocity overshoot passes checks
        self.observation_space = spaces.Box(
            low=-2.0, high=2.0, shape=(OBS_DIM,), dtype=np.float32
        )

        self.game = Game(headless=True, seed=seed)
        self.game.load()

        self._prev_score = 0
        self._prev_health = MAX_HEALTH
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

        # max(0): a new wave spawning raises total enemy hp, don't penalize that
        enemy_health_after = sum(e.health for e in self.game.enemies if e.alive)
        self._prev_enemy_health = enemy_health_after
        damage_dealt = max(0, enemy_health_before - enemy_health_after)

        terminated = self.game.state == STATE_GAME_OVER
        truncated = self._steps >= MAX_EPISODE_STEPS

        reward = (
            1.5 * damage_dealt
            + 0.03 * score_delta
            - 1.0 * max(0, -health_delta)
            - 0.001
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


def _nearest_enemy(game):
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
    p = game.player
    enemy, dead_count = _nearest_enemy(game)

    if enemy is not None:
        dx = (enemy.center[0] - p.center[0]) / DISPLAY_WIDTH
        dy = (enemy.center[1] - p.center[1]) / DISPLAY_HEIGHT
        enemy_alive = 1.0
        enemy_attacking = 1.0 if enemy.attacking else 0.0
        enemy_cd_frac = np.clip(enemy.melee_cd / max(enemy.melee_cooldown_base, 1e-6), 0.0, 1.0)
    else:
        dx = dy = 0.0
        enemy_alive = 0.0
        enemy_attacking = 0.0
        enemy_cd_frac = 0.0

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
        np.clip(p.attack_cd / ATTACK_COOLDOWN, 0.0, 1.0),
        np.clip(p.invuln / INVULN_TIME, 0.0, 1.0),
        1.0 if p.dashing else 0.0,
        np.clip(p.dash_cd / DASH_COOLDOWN, 0.0, 1.0),
        np.clip(dx, -2.0, 2.0),
        np.clip(dy, -2.0, 2.0),
        enemy_alive,
        enemy_attacking,
        enemy_cd_frac,
        np.clip(level_progress, 0.0, 1.0),
    ], dtype=np.float32)
