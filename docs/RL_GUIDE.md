# Neural-Ronin RL Training Guide

Everything you need to train, watch, and debug an AI that plays neural-ronin.
Written so you can come back in 3 months and pick it all up again from zero.

Every command in this file is run **from the project root** (`neural-ronin/`),
in a terminal, with your normal Python. That matters — the code does
`from main import Game`, so Python has to be standing in the project root to find it.

---

## 1. The big picture

Reinforcement learning (RL) is a loop:

```
        ┌─────────────────────────────────────────────┐
        │                                             │
        ▼                                             │
   ┌─────────┐   observation (17 numbers)   ┌──────────────┐
   │  AGENT   │ ◄──────────────────────────  │  ENVIRONMENT │
   │ (neural  │                              │  (the game,  │
   │ network) │ ──────────────────────────►  │  headless)   │
   └─────────┘   action (1 of 12 buttons)   └──────────────┘
                                              also returns: reward (a score
                                              for how good that step was)
```

Sixty times per simulated second, the agent looks at 17 numbers describing the
game state, picks one of 12 button combinations, and the game advances one tick.
The game hands back a **reward** — positive for damaging enemies, negative for
getting hit or dying. The training algorithm (**PPO**) slowly adjusts the neural
network so actions that led to high reward become more likely.

That's the whole thing. Everything below is details of those three boxes.

### The three layers of code

| Layer | File | Job |
|---|---|---|
| The game | [main.py](../main.py) | The actual samurai game. Has a special **headless mode** (no window, fixed 60Hz timestep, deterministic). |
| The environment wrapper | [rl/env.py](../rl/env.py) | Translates "game" into the standard RL interface (Gymnasium): builds the 17-number observation, computes the reward, defines the 12 actions. |
| The trainer | [rl/train.py](../rl/train.py) | Creates the environment, runs PPO from Stable-Baselines3 on it, saves/loads the model, and has `--eval` and `--watch` modes. |

---

## 2. Requirements

Already installed on this machine (checked July 2026):

- Python 3.12, `pygame`, `pytmx`
- `stable-baselines3` 2.8.0 — the PPO implementation
- `torch` 2.12.0 — the neural-network library underneath
- `gymnasium` — the standard RL environment interface
- `tensorboard` — live graphs of training progress

If you ever need to reinstall on a fresh machine:

```bash
pip install pygame pytmx stable-baselines3 gymnasium torch tensorboard
```

---

## 3. Quick start — the commands, in order

### Step 0 — delete the old model (one time, important)

The checkpoint currently in `rl/models/` was trained **before** the July 2026
physics fix, when headless physics accidentally ran 6x too fast. It learned to
play a different game. It is worthless. Delete it and the old graphs:

```bash
rm rl/models/ppo_neural_ronin.zip
rm -rf rl/logs/*
```

### Step 1 — smoke-test training (2 minutes)

A tiny run to confirm the pipeline works end to end:

```bash
python -m rl.train --timesteps 100000
```

You'll see a table print every few seconds (that's PPO reporting). When it
finishes, it prints `saved -> .../rl/models/ppo_neural_ronin`. 100k steps is
**not** enough to learn to fight — this is just a plumbing check.

### Step 2 — a real training run

```bash
python -m rl.train --timesteps 2000000
```

2 million steps is a reasonable first serious run. On a Mac, add `caffeinate`
so the machine doesn't sleep mid-run:

```bash
caffeinate -i python -m rl.train --timesteps 2000000
```

How long will it take? Look at the `fps` line in the printed table — that's
environment steps per second. Total time ≈ `timesteps / fps`. (e.g. at 1,000
fps, 2M steps ≈ 33 minutes.)

### Step 3 — watch the graphs while it trains

In a **second terminal**:

```bash
tensorboard --logdir rl/logs
```

Then open <http://localhost:6006> in your browser. See section 8 for what the
graphs mean. Leave it running; it refreshes as training progresses.

### Step 4 — evaluate the trained model (headless, prints numbers)

```bash
python -m rl.train --eval
```

Runs one 30-second episode with the saved model and prints
`episode reward=…  score=…  level=…`.

### Step 5 — watch it play in the real game window

```bash
python -m rl.train --watch
```

Opens the actual pygame window and lets the trained agent drive the samurai.
Close the window with the X button. If it dies, it auto-restarts.

### Bonus — play the game yourself

```bash
python main.py
```

### Useful flags

Both training and eval accept `--seed N` (default 0) to change the random seed:

```bash
python -m rl.train --timesteps 2000000 --seed 7
python -m rl.train --eval --seed 7
```

Same seed = exactly the same game every time (see section 5 on determinism).

---

## 4. How the game becomes a training environment

Training needs to run the game **millions of times faster than real-time
watching would allow**, and needs every run to be **repeatable**. That's what
headless mode in [main.py](../main.py) is:

- **No window.** `SDL_VIDEODRIVER=dummy` lets pygame load sprites without
  opening a display. Nothing is ever drawn to screen (drawing is most of the
  CPU cost of a game).
- **Fixed timestep.** Live play ticks at whatever your monitor gives it;
  headless always advances exactly `SIM_DT = 1/60` of a second per `step()`.
  Same physics every run.
- **Simulated clock.** Animations are timed off `game.sim_time_ms` (a counter
  the game itself advances) instead of the real wall clock, so animation frames
  land on the same ticks every run.
- **Scripted input.** Instead of a keyboard, a `ScriptedInputSource`
  ([scripts/input_adapter.py](../scripts/input_adapter.py)) holds whatever
  buttons the agent chose this tick.
- **Seeded randomness.** All gameplay randomness (enemy spawn positions, speed
  jitter) comes from `game.rng`, a `random.Random(seed)`. Same seed → identical
  episode. This was verified: a 300-step rollout is bit-for-bit identical
  across resets.
- **No side effects.** Headless mode never writes `config/high_score.json`
  (your human high score is safe) and skips particle effects entirely.

The env in [rl/env.py](../rl/env.py) then wraps this in the standard
[Gymnasium API](https://gymnasium.farama.org/api/env/): `reset()` starts an
episode, `step(action)` advances one tick and returns
`(observation, reward, terminated, truncated, info)`.

An episode ends two ways:

- **terminated** — the player died (game over).
- **truncated** — hit the step limit `MAX_EPISODE_STEPS = 3600` (60 sim-seconds)
  without dying. Truncation stops episodes from running forever.

### ⚠️ The one-env-per-process rule

The game engine (pygpen) keeps its internals in **process-global singletons**.
Creating two `GameEnv`s in the same Python process would silently cross-wire
them, so the second one now **raises `RuntimeError` on purpose**. If you ever
want parallel environments, use `SubprocVecEnv` (one OS process per env), never
`DummyVecEnv` / `make_vec_env`:
<https://stable-baselines3.readthedocs.io/en/master/guide/vec_envs.html>

---

## 5. What the agent sees — the 17 observations

Built in `build_obs()` at the bottom of [rl/env.py](../rl/env.py). Every value
is normalized to roughly −1…1 (neural networks train badly on raw pixels
coordinates like `942.0`; they like small numbers).

"Nearest enemy" = the living enemy closest to the player horizontally.

| # | Value | Meaning |
|---|---|---|
| 0 | `player_x / map_w` | Where am I horizontally? 0 = left edge, 1 = right edge |
| 1 | `player_y / map_h` | Where am I vertically? |
| 2 | `velocity_x / RUN_SPEED` | How fast am I moving sideways (and which way)? |
| 3 | `velocity_y / MAX_FALL` | Am I rising (negative) or falling (positive)? |
| 4 | `health / MAX_HEALTH` | My health, 0…1 |
| 5 | in air? | 1.0 if airborne (air_time > 0.08s), else 0.0 |
| 6 | attacking? | 1.0 while my sword swing animation is playing |
| 7 | `attack_cd / ATTACK_COOLDOWN` | 0 = can swing right now, 1 = just swung |
| 8 | `invuln / INVULN_TIME` | Am I in post-hit invincibility frames? |
| 9 | dashing? | 1.0 mid-dodge (dash has i-frames) |
| 10 | `dash_cd / DASH_COOLDOWN` | 0 = can dash right now, 1 = just dashed |
| 11 | `dx` to nearest enemy | Horizontal distance, screen-widths. Sign = direction |
| 12 | `dy` to nearest enemy | Vertical distance |
| 13 | enemy alive? | 0.0 means "no enemies right now" (wave break) — then 11-16 are zeros |
| 14 | enemy attacking? | 1.0 while the nearest enemy is winding up / swinging |
| 15 | enemy attack cooldown | 0 = enemy ready to swing again, 1 = it just swung |
| 16 | level progress | 0…1, how much of the current level's waves are cleared |

What the agent does **not** see: other enemies beyond the nearest one, the
wave/phase banners, the score. Keep this table in mind when the agent behaves
oddly — it can't react to what it can't see.

---

## 6. What the agent can do — the 12 actions

The `ACTIONS` list at the top of [rl/env.py](../rl/env.py). One action per
tick; each is a set of "buttons held this tick":

| # | Buttons | | # | Buttons |
|---|---|---|---|---|
| 0 | nothing | | 6 | right + jump |
| 1 | left | | 7 | left + attack |
| 2 | right | | 8 | right + attack |
| 3 | jump | | 9 | dash |
| 4 | attack | | 10 | left + dash |
| 5 | left + jump | | 11 | right + dash |

The combos exist because a human holds run while jumping/attacking.
Left+right together is excluded (they cancel out in the player code).

---

## 7. The reward — what "good" means

In `GameEnv.step()` in [rl/env.py](../rl/env.py):

```
reward = 1.5 × enemy HP removed this tick     ← the main signal: hit things
       + 0.03 × score gained this tick         ← small bonus for kills/waves/levels
       − 1.0 × health lost this tick           ← getting hit is bad
       − 0.001                                 ← tiny cost per tick: don't stall forever
       − 5.0 if the player died this tick      ← dying is very bad
```

Why these shapes:

- **Damage dealt (1.5/HP)** is *dense* — it fires on every successful sword hit,
  so the agent gets feedback constantly, not just at kills. Dense reward = much
  faster learning.
- **Score (0.03×)** is small on purpose. A kill is 100–220 score → about +3–6.6
  reward. It's a topper on the damage signal, not the main dish.
- **Health lost (−1.0/HP)** makes trading hits unprofitable unless the agent
  deals more than it takes.
- **The −0.001/tick time cost** means hiding in a corner slowly bleeds reward.
  Over a full 3600-tick episode it's only −3.6, so it nudges rather than
  dominates.
- **−5 on death** makes survival matter beyond just the lost future rewards.

This is the single most important thing to tune. The agent optimizes *exactly*
this formula, including any loopholes in it — not what you meant by it.

---

## 8. Reading the TensorBoard graphs

```bash
tensorboard --logdir rl/logs     # then open http://localhost:6006
```

The ones that matter, in order of importance:

| Graph | What it is | What you want |
|---|---|---|
| `rollout/ep_rew_mean` | Average episode reward (recent 100 episodes) | **The** number. Should trend up. Flat forever = learning failed. |
| `rollout/ep_len_mean` | Average episode length in ticks | Should rise toward 3600 (surviving longer) as it learns not to die. |
| `train/explained_variance` | How well the value network predicts returns | Should climb toward ~0.8–1. Near 0 or negative late in training = something's off. |
| `train/entropy_loss` | How random the policy still is | Slowly rises toward 0 (less random) as the agent commits to a strategy. Crashing to 0 very early = premature convergence — consider raising `ent_coef`. |
| `train/approx_kl` | How big each policy update is | Small and stable (~0.005–0.03). Huge spikes = learning rate too high. |
| `time/fps` | Environment steps per second | Just for estimating run time. |

The same numbers also print as a text table in the training terminal.

More detail: [SB3 TensorBoard guide](https://stable-baselines3.readthedocs.io/en/master/guide/tensorboard.html)
and [SB3 logger metric definitions](https://stable-baselines3.readthedocs.io/en/master/common/logger.html).

---

## 9. The PPO hyperparameters, line by line

From `train()` in [rl/train.py](../rl/train.py):

```python
model = PPO(
    "MlpPolicy",          # a plain multi-layer perceptron: 17 in → 64 → 64 → 12 out
    env,
    seed=seed,            # seeds torch + the algorithm, for repeatable training
    verbose=1,            # print the stats table
    tensorboard_log=...,  # where the graphs go
    n_steps=4096,         # collect 4096 ticks of play before each learning update
    batch_size=128,       # chop those 4096 into minibatches of 128 for gradient steps
    n_epochs=10,          # reuse each 4096-tick batch 10 times before throwing it away
    gamma=0.99,           # discount: reward n ticks in the future is worth 0.99^n now.
                          #   0.99 at 60Hz ≈ caring about the next ~1.7 seconds strongly
    ent_coef=0.01,        # entropy bonus: pay the agent a little to stay random/exploring
    learning_rate=3e-4,   # step size of the neural-net updates. The classic default
)
```

Rules of thumb if you tune these:

- Agent converges to something dumb and stops exploring → raise `ent_coef`
  (try 0.02–0.05).
- Learning is unstable (reward crashes after rising, `approx_kl` spikes) →
  lower `learning_rate` (try 1e-4).
- Reward signal is sparse/long-horizon (e.g. you remove damage reward and keep
  only kills) → raise `gamma` to 0.995–0.999 and consider larger `n_steps`.

Full reference: [SB3 PPO docs](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html).
The original paper: [Schulman et al., 2017 — Proximal Policy Optimization](https://arxiv.org/abs/1707.06347).

---

## 10. How to change things (recipes)

### Change the reward

Edit the `reward = (...)` block in `GameEnv.step()`
([rl/env.py](../rl/env.py)). Then retrain from scratch — a model trained on
an old reward is meaningless under a new one:

```bash
rm rl/models/ppo_neural_ronin.zip
python -m rl.train --timesteps 2000000
```

### Add an observation feature

1. Append the value to the array in `build_obs()` ([rl/env.py](../rl/env.py)).
   Normalize it to roughly −1…1 like the others.
2. Bump `OBS_DIM` (currently 17) to match. If they disagree, SB3's `check_env`
   fails immediately with a shape error — that's your safety net.
3. Retrain from scratch (the old network has the wrong input size and won't
   even load against the new env).

### Add an action

Append a dict to `ACTIONS` ([rl/env.py](../rl/env.py)) using the key names
from `INPUT_KEYS` in [main.py](../main.py):
`left, right, jump, attack, dash, confirm, menu`. Retrain from scratch (the
network's output layer size changes).

### Make training start on a harder level (curriculum idea)

Not built yet. The hook point is `Game.start_run()` in [main.py](../main.py),
which hardcodes `self.level = 1`. Give it a `start_level` parameter, thread it
through `Game.reset()` / `GameEnv.reset(options=...)`, and you can train "level
3 only" specialists or ramp difficulty as win-rate rises.

### Continue training an existing model (instead of from scratch)

`train()` currently always creates a fresh model. To resume, replace the
`model = PPO(...)` lines with:

```python
model = PPO.load(str(MODEL_PATH), env=env)
```

and call `model.learn(..., reset_num_timesteps=False)` so the tensorboard
x-axis continues instead of restarting at 0.

---

## 11. Rules that keep everything working

1. **Always run from the project root.** `python -m rl.train`, not
   `cd rl && python train.py`.
2. **One `GameEnv` per process.** The second one raises on purpose.
   Parallel = `SubprocVecEnv`.
3. **Reward, `OBS_DIM`, or `ACTIONS` changed → retrain from scratch.**
   Old checkpoints are lies after any of those change.
4. **Anything trained before the July 2026 physics fix is invalid** (it
   learned 6x-speed physics). If in doubt about a checkpoint's age, delete it.
5. **Don't add wall-clock time or unseeded randomness to gameplay code.**
   Gameplay randomness goes through `game.rng`; time through `game.sim_time_ms`
   / `game.dt`. Cosmetic-only randomness (particles) uses its own RNG stream so
   it can't shift enemy spawns.
6. **Test determinism after touching game code.** Two rollouts with the same
   seed and same actions must produce identical observations. (There's a
   ready-made check in the smoke script pattern — a 300-step seeded rollout
   compared with `np.array_equal`.)

---

## 12. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `ModuleNotFoundError: No module named 'rl'` or `'main'` | You're not in the project root. `cd` there first. |
| `RuntimeError: Only one GameEnv per process` | Something created a second env (e.g. `make_vec_env`, or `check_env` on a *second* env instance). One env per process; parallel = `SubprocVecEnv`. |
| `--eval` / `--watch` crashes with "No such file … ppo_neural_ronin" | No trained model saved yet. Run training first. |
| Reward graph flat at ~0 for a long time | Normal for the first ~100k steps (random flailing). If flat past ~500k: reward may be too sparse or a bug — run `--eval` and read the printed score, check the agent isn't just standing still. |
| Agent runs to a corner and sits there | It learned that avoiding damage beats seeking it. Raise the damage-dealt weight, the time cost, or add an approach-shaping term (reward for decreasing distance to nearest enemy). |
| Training suddenly at NaN / reward collapses | Learning rate too high for the current reward scale. Lower `learning_rate`, check reward isn't producing huge values. |
| Everything is slow | Check `time/fps` in the logs. Headless should be thousands of fps. If it's low, something is doing per-tick rendering or file I/O that shouldn't be. |
| Mac went to sleep mid-run | Use `caffeinate -i python -m rl.train ...` |

---

## 13. Links

**The libraries this project uses**

- Gymnasium (the env API): <https://gymnasium.farama.org/> — especially
  [Env API](https://gymnasium.farama.org/api/env/) and
  [Spaces](https://gymnasium.farama.org/api/spaces/)
- Stable-Baselines3: <https://stable-baselines3.readthedocs.io/> — especially
  [PPO](https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html),
  [Custom environments](https://stable-baselines3.readthedocs.io/en/master/guide/custom_env.html),
  [Vectorized envs](https://stable-baselines3.readthedocs.io/en/master/guide/vec_envs.html),
  [TensorBoard](https://stable-baselines3.readthedocs.io/en/master/guide/tensorboard.html),
  [Callbacks (checkpoint/eval)](https://stable-baselines3.readthedocs.io/en/master/guide/callbacks.html)
- pygame: <https://www.pygame.org/docs/>

**Learning RL concepts properly**

- OpenAI Spinning Up (best intro to RL math, free):
  <https://spinningup.openai.com/en/latest/spinningup/rl_intro.html> and its
  [PPO page](https://spinningup.openai.com/en/latest/algorithms/ppo.html)
- The PPO paper: <https://arxiv.org/abs/1707.06347>
- Reward-design war stories ("specification gaming" — agents exploiting reward
  loopholes, very relevant to section 7):
  <https://deepmind.google/discover/blog/specification-gaming-the-flip-side-of-ai-ingenuity/>

**The game engine**

- pygpen is vendored in [scripts/pygpen/](../scripts/pygpen/) — it's
  DaFluffyPotato's engine: <https://dafluffypotato.com/>
