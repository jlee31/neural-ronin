from rl.env import GameEnv

# TODO: swap in whichever RL library you use (stable-baselines3, cleanrl, etc.)
# Example with stable-baselines3:
#
# from stable_baselines3 import PPO
# env = GameEnv()
# model = PPO("MlpPolicy", env, verbose=1, tensorboard_log="rl/logs/")
# model.learn(total_timesteps=100_000)
# model.save("rl/models/ppo_game")

if __name__ == '__main__':
    env = GameEnv()
    obs, _ = env.reset()
    print("Environment loaded. Observation shape:", obs.shape)
    print("Action space:", env.action_space)
