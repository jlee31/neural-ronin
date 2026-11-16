# RL guide

How the game is wrapped as an RL environment, how to train, and how to change things.
All commands run from the project root (`rl/` imports `main`).

## Layout

| File | Role |
|---|---|
| `main.py` | The game. `Game(headless=True, seed=N)` runs without a window at a fixed 60Hz step. |
| `rl/env.py` | Gymnasium wrapper: observation, reward, action set. |
| `rl/train.py` | PPO (Stable-Baselines3) trainer with `--eval` and `--watch`. |

## Commands

```bash
python -m rl.train --timesteps 40000    # quick pipeline check
python -m rl.train                      # 2M steps, 8 workers, seed 0
python -m rl.train --timesteps 10000000 --n-envs 8 --seed 3
caffeinate -i python -m rl.train        # macOS: keep the machine awake
tensorboard --logdir rl/logs            # http://localhost:6006
python -m rl.train --eval               # one 30s headless episode, prints reward/score/level
python -m rl.train --watch              # agent plays in the real window, restarts on death
```

Outputs under `rl/models/`:

- `best/best_model.zip`: best model by a 5-episode eval every 100k steps. `--eval` and `--watch` prefer this.
- `checkpoints/`: rolling saves every 500k steps.
- `ppo_neural_ronin.zip`: model at the end of the run.

Measured throughput on an M-series Mac is roughly 11k env steps/s with 8 workers,
so 2M steps takes a few minutes.

## Headless mode

- `SDL_VIDEODRIVER=dummy` so pygame loads sprites without a window. Nothing is drawn.
- Fixed `SIM_DT = 1/60` per `step()`.
- Animations are timed off `game.sim_time_ms`, not the wall clock.
- Input comes from `ScriptedInputSource` (`scripts/input_adapter.py`).
- All gameplay randomness goes through `game.rng` (`random.Random(seed)`). Same seed and
  actions give identical observations.
- Headless never writes `config/high_score.json` and skips particles.

Episodes end on player death (`terminated`) or after `MAX_EPISODE_STEPS = 3600`
ticks (`truncated`).

### One env per process

pygpen keeps its engine state in process-global singletons, so `GameEnv` raises if a
second one is created in the same process. Parallel training uses `SubprocVecEnv`
with `start_method="spawn"` (fork hangs on macOS once pygame is loaded). Don't use
`DummyVecEnv` or `make_vec_env`.

## Observation (17 floats, roughly in [-1, 1])

"Nearest enemy" is the living enemy closest to the player horizontally.

| # | Value |
|---|---|
| 0 | player x / map width |
| 1 | player y / map height |
| 2 | player vx / RUN_SPEED |
| 3 | player vy / MAX_FALL |
| 4 | health / MAX_HEALTH |
| 5 | airborne (air_time > 0.08s) |
| 6 | attacking |
| 7 | attack cooldown fraction (0 = ready) |
| 8 | invulnerability fraction |
| 9 | dashing |
| 10 | dash cooldown fraction (0 = ready) |
| 11 | dx to nearest enemy / screen width |
| 12 | dy to nearest enemy / screen height |
| 13 | nearest enemy alive (0 during wave breaks; 11-16 are then 0) |
| 14 | nearest enemy attacking (windup or swing) |
| 15 | nearest enemy attack cooldown fraction |
| 16 | level progress (waves cleared, 0..1) |

The agent does not see other enemies, banners or the score.

## Actions (12)

| # | Buttons | # | Buttons |
|---|---|---|---|
| 0 | none | 6 | right + jump |
| 1 | left | 7 | left + attack |
| 2 | right | 8 | right + attack |
| 3 | jump | 9 | dash |
| 4 | attack | 10 | left + dash |
| 5 | left + jump | 11 | right + dash |

Buttons are "held this tick". Attack, jump and dash trigger on the press edge, so
holding attack swings once; the agent has to release and press again.

## Reward

```
reward = 1.5 * enemy hp removed this tick
       + 0.03 * score gained this tick
       - 1.0 * player hp lost this tick
       - 0.001
       - 5.0 on death
```

Damage dealt is the dense signal. Score is a small kill bonus. The per-tick cost is
-3.6 over a full episode. Change the reward, `OBS_DIM` or `ACTIONS` and the old
model is invalid: delete `rl/models/*` and retrain.

## PPO settings

```python
PPO("MlpPolicy", env, seed=seed, device="cpu", n_steps=1024, batch_size=256,
    n_epochs=10, gamma=0.99, ent_coef=0.01, learning_rate=3e-4)
```

`n_steps` is per worker (8192 ticks per update with 8 workers). The network is tiny,
so CPU is faster than MPS. If the policy collapses to one behaviour early, raise
`ent_coef`; if reward crashes after rising or `approx_kl` spikes, lower the learning rate.

## Tensorboard

- `rollout/ep_rew_mean`: should trend up.
- `rollout/ep_len_mean`: should approach 3600 as it stops dying.
- `train/explained_variance`: should climb toward 1.
- `train/entropy_loss`: rises toward 0 as the policy commits. Hitting 0 very early is premature convergence.
- `train/approx_kl`: small and stable (~0.005-0.03).

## Changing things

- Reward: edit the `reward = (...)` block in `GameEnv.step()`, retrain.
- Observation: append to the array in `build_obs()`, bump `OBS_DIM`, retrain.
- Action: append a dict to `ACTIONS` using keys from `INPUT_KEYS` in `main.py`, retrain.
- Start on a later level: `Game.start_run()` hardcodes level 1; thread a `start_level`
  through `Game.reset()` and `GameEnv.reset(options=...)`.
- Resume training: `model = PPO.load(str(MODEL_PATH), env=env)` and
  `model.learn(..., reset_num_timesteps=False)`.

## Rules

1. Run from the project root.
2. One `GameEnv` per process; parallel means `SubprocVecEnv`.
3. No wall-clock time or unseeded randomness in gameplay code. Use `game.rng`,
   `game.sim_time_ms`, `game.dt`.
4. After touching game code, check determinism: two seeded rollouts with the same
   actions must give identical observations.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `No module named 'rl'` / `'main'` | Not in the project root. |
| `RuntimeError: Only one GameEnv per process` | Something made a second env in-process. |
| `--eval` / `--watch` can't find the model | Train first. |
| Reward flat past ~500k steps | Run `--eval`, check it isn't standing still; reward may be too sparse. |
| Agent hides in a corner | Raise the damage weight or time cost, or add a distance-shaping term. |
| NaN / reward collapse | Lower the learning rate. |
| Low fps | Something is rendering or doing file I/O per tick. |

## Links

- Gymnasium: https://gymnasium.farama.org/api/env/
- SB3 PPO: https://stable-baselines3.readthedocs.io/en/master/modules/ppo.html
- SB3 vec envs: https://stable-baselines3.readthedocs.io/en/master/guide/vec_envs.html
- SB3 callbacks: https://stable-baselines3.readthedocs.io/en/master/guide/callbacks.html
- PPO paper: https://arxiv.org/abs/1707.06347
- Spinning Up: https://spinningup.openai.com/en/latest/algorithms/ppo.html
- pygpen (vendored in `scripts/pygpen/`): https://dafluffypotato.com/
