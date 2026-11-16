"""
PPO training for neural-ronin. Run from the project root:

    python -m rl.train                  # train (2M steps, 8 workers)
    python -m rl.train --eval           # one headless episode with the saved model
    python -m rl.train --watch          # watch the saved model play in a window

Saves rl/models/ppo_neural_ronin.zip (final), rl/models/best/best_model.zip
(best by periodic eval) and rl/models/checkpoints/. Tensorboard logs in rl/logs.
"""

import argparse
import pathlib

from stable_baselines3 import PPO
from stable_baselines3.common.callbacks import CheckpointCallback, EvalCallback
from stable_baselines3.common.vec_env import SubprocVecEnv, VecMonitor

from rl.env import GameEnv, ACTIONS, build_obs

MODELS_DIR = pathlib.Path(__file__).resolve().parent / "models"
MODEL_PATH = MODELS_DIR / "ppo_neural_ronin"
BEST_DIR = MODELS_DIR / "best"
CKPT_DIR = MODELS_DIR / "checkpoints"
LOG_DIR = pathlib.Path(__file__).resolve().parent / "logs"

EVAL_EVERY_TOTAL = 100_000
CKPT_EVERY_TOTAL = 500_000


def make_env(seed, rank):
    def _init():
        return GameEnv(seed=seed + rank)
    return _init


def train(timesteps, seed, n_envs):
    # one process per env (pygpen singletons); spawn because fork hangs with pygame on macOS
    env = VecMonitor(
        SubprocVecEnv([make_env(seed, i) for i in range(n_envs)], start_method="spawn")
    )
    eval_env = VecMonitor(
        SubprocVecEnv([make_env(seed + 10_000, 0)], start_method="spawn")
    )

    # callback freqs are in per-worker steps
    callbacks = [
        EvalCallback(
            eval_env,
            best_model_save_path=str(BEST_DIR),
            log_path=str(LOG_DIR / "eval"),
            eval_freq=max(EVAL_EVERY_TOTAL // n_envs, 1),
            n_eval_episodes=5,
            deterministic=True,
        ),
        CheckpointCallback(
            save_freq=max(CKPT_EVERY_TOTAL // n_envs, 1),
            save_path=str(CKPT_DIR),
            name_prefix="ppo",
        ),
    ]

    model = PPO(
        "MlpPolicy",
        env,
        seed=seed,
        verbose=1,
        device="cpu",
        tensorboard_log=str(LOG_DIR),
        n_steps=1024,
        batch_size=256,
        n_epochs=10,
        gamma=0.99,
        ent_coef=0.01,
        learning_rate=3e-4,
    )
    try:
        model.learn(total_timesteps=timesteps, callback=callbacks)
        model.save(str(MODEL_PATH))
        print(f"saved -> {MODEL_PATH}")
        print(f"best  -> {BEST_DIR / 'best_model.zip'}")
    finally:
        env.close()
        eval_env.close()


def load_model(env=None):
    best = BEST_DIR / "best_model.zip"
    path = best if best.exists() else MODEL_PATH
    print(f"loading {path}")
    return PPO.load(str(path), env=env)


def evaluate(seed):
    env = GameEnv(seed=seed)
    model = load_model(env=env)
    obs, _ = env.reset(seed=seed)
    total = 0.0
    for _ in range(60 * 30):
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total += reward
        if terminated or truncated:
            break
    print(f"episode reward={total:.2f}  score={info['score']}  level={info['level']}")


def watch(seed):
    # pygpen's Input polls pygame events (incl. QUIT), so don't poll them here
    from main import Game, STATE_PLAYING, INPUT_KEYS
    from scripts.input_adapter import ScriptedInputSource

    game = Game(headless=False, seed=seed)
    game.load()
    game.input_source = ScriptedInputSource(INPUT_KEYS)
    game.start_run()
    game.state = STATE_PLAYING

    model = load_model()

    while True:
        obs = build_obs(game)
        action, _ = model.predict(obs, deterministic=True)
        game.input_source.set_actions(ACTIONS[int(action)])
        game.update()
        if not game.player.alive:
            game.start_run()
            game.state = STATE_PLAYING


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--timesteps", type=int, default=2_000_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--n-envs", type=int, default=8)
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()

    if args.watch:
        watch(args.seed)
    elif args.eval:
        evaluate(args.seed)
    else:
        train(args.timesteps, args.seed, args.n_envs)
