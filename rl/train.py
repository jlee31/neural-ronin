"""
Train a PPO agent on neural-ronin.

Run from project root:
    python -m rl.train

CLI:
    --timesteps N   total environment steps (default 100_000)
    --seed N        env + algo seed (default 0)
    --eval          skip training, run one headless rollout, print final score
    --watch         skip training, open the game window and watch the agent play
"""

import argparse
import pathlib

from stable_baselines3 import PPO
from stable_baselines3.common.env_checker import check_env

from rl.env import GameEnv, ACTIONS, build_obs

MODEL_PATH = pathlib.Path(__file__).resolve().parent / "models" / "ppo_neural_ronin"
LOG_DIR = pathlib.Path(__file__).resolve().parent / "logs"


def train(timesteps, seed):
    env = GameEnv(seed=seed)
    check_env(env, warn=True)

    model = PPO(
        "MlpPolicy",
        env,
        seed=seed,
        verbose=1,
        tensorboard_log=str(LOG_DIR),
        n_steps=4096,       # longer rollout = better advantage estimates
        batch_size=128,
        n_epochs=10,
        gamma=0.99,
        ent_coef=0.01,      # entropy bonus keeps the agent exploring
        learning_rate=3e-4,
    )
    model.learn(total_timesteps=timesteps, progress_bar=False)
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save(str(MODEL_PATH))
    print(f"saved -> {MODEL_PATH}")


def evaluate(seed):
    env = GameEnv(seed=seed)
    model = PPO.load(str(MODEL_PATH), env=env)
    obs, _ = env.reset(seed=seed)
    total = 0.0
    for _ in range(60 * 30):  # 30 sim-seconds
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total += reward
        if terminated or truncated:
            break
    print(f"episode reward={total:.2f}  score={info['score']}  level={info['level']}")


def watch(seed):
    """Open the real pygame window and let the trained agent drive the player.

    pygpen's Input.update() polls pygame events itself (including QUIT), so the
    user closes the window with the X button. We don't poll events here — that
    would steal them from pygpen.
    """
    from main import Game, STATE_PLAYING, INPUT_KEYS
    from scripts.input_adapter import ScriptedInputSource

    game = Game(headless=False, seed=seed)
    game.load()
    game.input_source = ScriptedInputSource(INPUT_KEYS)
    game.start_run()
    game.state = STATE_PLAYING

    model = PPO.load(str(MODEL_PATH))

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
    parser.add_argument("--timesteps", type=int, default=100_000)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--eval", action="store_true")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()

    if args.watch:
        watch(args.seed)
    elif args.eval:
        evaluate(args.seed)
    else:
        train(args.timesteps, args.seed)
