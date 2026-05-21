# RL handoff

This file documents the headless game API and what still needs to be built before
training a real agent. Phase 3 of [roadmap.md](roadmap.md).

The **foundation** is done — the game is deterministic, headless-capable, and
steps at a fixed timestep. The **env wrapper, observation, reward, and action
mapping** are not. This doc covers both: what exists, and what you (or a future
agent) needs to add.

---

## What's already in place

### `Game` runs in two modes

```python
# Live play (default) — opens a window, variable dt, reads pygame events
Game().run()

# Headless RL — no window, fixed 60Hz tick, dict-driven input
g = Game(headless=True, seed=42)
g.load()
g.reset()
g.step({"right": True, "attack": True})
```

Behind the scenes:
- `headless=True` sets `SDL_VIDEODRIVER=dummy` before `pp.init()`, so pygame can
  still load sprites without opening a window.
- `seed` is stored on a `random.Random` instance owned by the game. Anything
  stochastic (currently just `HitVFX` particles) must take that RNG so episodes
  are reproducible.
- `g.sim_time_ms` replaces `pygame.time.get_ticks()` across the codebase.
  Animation timers read from it, so playback at the same seed + same actions
  produces the same pixels.

### One step = one tick at 1/60s

`g.step(actions)` calls `g._tick(SIM_DT)` where `SIM_DT = 1/60`. The tick:
1. Writes `actions` into `g.input_source` (a `ScriptedInputSource`).
2. Advances `sim_time_ms` by 16ms.
3. Routes to `_tick_playing` / menu / game-over depending on `g.state`.

`actions` is a dict like `{"left": bool, "right": bool, "jump": bool,
"attack": bool, "confirm": bool, "menu": bool}`. Missing keys default to `False`.
The valid set is in `INPUT_KEYS` at the top of `main.py`.

### Determinism verified

```bash
python -c "
import os; os.environ['SDL_VIDEODRIVER']='dummy'
from main import Game
g1 = Game(headless=True, seed=42); g1.load(); g1.reset()
g2 = Game(headless=True, seed=42); g2.load(); g2.reset()
for _ in range(60):
    g1.step({'right': True}); g2.step({'right': True})
assert g1.player.pos == g2.player.pos, 'NOT deterministic'
print('ok')
"
```

If this ever breaks, look for: bare `random.*` calls (must go through
`game.rng`), or new `pygame.time.get_ticks()` calls (must use
`game.sim_time_ms`).

---

## What you still need to build

### 1. Gymnasium env wrapper (`rl/env.py`)

The skeleton at `rl/env.py` is a TODO stub. Fill it in along these lines:

```python
import gymnasium as gym
from gymnasium import spaces
import numpy as np

from main import Game, INPUT_KEYS

ACTIONS = [
    {},                                    # 0: noop
    {"left": True},                        # 1: left
    {"right": True},                       # 2: right
    {"jump": True},                        # 3: jump
    {"attack": True},                      # 4: attack
    {"left": True,  "jump": True},         # 5: left+jump
    {"right": True, "jump": True},         # 6: right+jump
    {"left": True,  "attack": True},       # 7: left+attack
    {"right": True, "attack": True},       # 8: right+attack
]

class NeuralRoninEnv(gym.Env):
    def __init__(self, seed=None, max_steps=3600):
        self.game = Game(headless=True, seed=seed)
        self.game.load()
        self.action_space = spaces.Discrete(len(ACTIONS))
        # observation_space depends on the obs format you choose — see below
        self.max_steps = max_steps
        self._steps = 0

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.game.reset(seed=seed)
        self._steps = 0
        return self._get_obs(), {}

    def step(self, action):
        self.game.step(ACTIONS[action])
        self._steps += 1
        obs = self._get_obs()
        reward = self._get_reward()
        terminated = not self.game.player.alive
        truncated = self._steps >= self.max_steps
        return obs, reward, terminated, truncated, {}
```

### 2. Observation: pixel frames (CNN path was chosen)

Render the game's `display` Surface to a numpy array each step. Don't include the
HUD or menu overlays — the agent should only see the world.

```python
import pygame

def _get_obs(self):
    # Render world only (no HUD), then snapshot the surface to numpy.
    g = self.game
    g.display.fill((0, 0, 0))
    g._draw_world()
    arr = pygame.surfarray.array3d(g.display)        # (W, H, 3) uint8
    arr = arr.transpose(1, 0, 2)                     # → (H, W, 3) — standard
    # Optional: downscale (84×84 grayscale is the Atari convention)
    return arr
```

Observation space: `spaces.Box(0, 255, shape=(H, W, 3), dtype=np.uint8)`.
Atari-style CNNs train ~10× faster on 84×84 grayscale than on 640×360 RGB —
worth doing once you confirm the full-res version learns anything at all.

Performance note: pixel obs is ~100× slower per step than a feature vector. If
training feels too slow, consider building a parallel `feature` obs path:
`[player_x, player_y, player_vx, player_vy, on_ground, attacking, health,
*per_enemy(dx, dy, alive, attacking)]`. All values are already on the entities.

### 3. Reward

Sparse score-only reward (just `self.game.score - prev_score`) probably won't
learn. Start with shaped reward:

```python
def _get_reward(self):
    r = 0.0
    r += (self.game.score - self._prev_score) * 0.01    # +1 per kill (score=100)
    r += (self.game.player.health - self._prev_health) * 0.5   # ±0.5 per hp delta
    r -= 0.001                                          # tiny step penalty
    if not self.game.player.alive:
        r -= 1.0                                        # death penalty
    self._prev_score = self.game.score
    self._prev_health = self.game.player.health
    return r
```

Initialize `_prev_score` and `_prev_health` in `reset()`. Tune coefficients
empirically — the dense terms should be small enough that the agent still cares
about the sparse kill bonus.

### 4. Training (`rl/train.py`)

```python
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from rl.env import NeuralRoninEnv

env = make_vec_env(lambda: NeuralRoninEnv(), n_envs=8)
model = PPO("CnnPolicy", env, tensorboard_log="rl/logs/", verbose=1)
model.learn(total_timesteps=1_000_000)
model.save("rl/models/ppo_ronin")
```

Smoke-test first with `total_timesteps=10_000` and one env to make sure the
pipeline runs end-to-end before scaling up.

---

## Gotchas to know about

- **Game state singleton.** `pp.PygpenGame` registers itself in a process-global
  `elems['singletons']['Game']`. You can't run two `Game` instances in the same
  process — the second clobbers the first. For vectorized training, use
  multiprocessing (one game per subprocess), which `make_vec_env` does by
  default with `SubprocVecEnv`.

- **Pygame init.** Even headless mode runs `pygame.init()` and creates a real
  display surface (via SDL's dummy driver). This is needed for sprite loading.
  If you ever see "video system not initialized" errors, make sure
  `SDL_VIDEODRIVER=dummy` is set *before* the first pygame call.

- **Episode boundaries.** Currently `g.state` flips to `STATE_GAME_OVER` when
  the player dies, but the player object stays around. The env wrapper should
  treat `not g.player.alive` as `terminated=True` and call `g.reset()` from the
  env's `reset()`, not by sending `confirm` to the in-game menu.

- **Level progression.** The game has multiple levels and a kill-counter
  per-level (see `scripts/levels.py`). For a first agent, decide: do you want
  episodes to span all levels, or terminate after level 1? The skeleton above
  assumes "one death = one episode," which crosses levels.

- **Particles.** `HitVFX` runs in headless mode (deterministic via the seeded
  RNG) but is invisible because there's no render path. The CPU cost is small.
  If you want to skip it for speed, gate `hit_vfx.spawn_player_hit` calls in
  `Player.take_damage` on `self.e['Game'].headless`.

- **Save file collisions.** `save_high_score()` writes to
  `config/high_score.json` on player death. Training will hammer this file. Add
  a `if not self.headless:` guard around the call in `_tick_playing`, or your
  saves will end up with whatever the last training run scored.

---

## File map

| File | Role in RL |
|---|---|
| `main.py` | `Game(headless, seed)`, `reset()`, `step(actions)` |
| `scripts/input_adapter.py` | `ScriptedInputSource` — how env actions reach the player |
| `scripts/hit_vfx.py` | Takes `rng=` for reproducibility — pattern for any future stochastic system |
| `scripts/player.py` | Reads `game.input_source`, `game.dt`, `game.sim_time_ms` — touch these, not pygame globals |
| `scripts/dummy_enemy.py` | Same as player |
| `rl/env.py` | TODO — Gymnasium env wrapper |
| `rl/train.py` | TODO — PPO training entrypoint |

---

## Quick checklist before kicking off real training

- [ ] Env wrapper in `rl/env.py` with `reset`/`step`/`_get_obs`/`_get_reward`
- [ ] Action mapping verified (run a random-action loop, watch the agent flail)
- [ ] Reward signal sanity-check: scripted "run right + attack" gets higher
      total reward than "do nothing"
- [ ] Headless save-file guard added (see Gotchas)
- [ ] Smoke train: 10k steps, single env, confirms pipeline
- [ ] Tensorboard logging working before scaling up
