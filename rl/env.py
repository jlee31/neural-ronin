import gymnasium as gym
import numpy as np
import pygame
from gymnasium import spaces


class GameEnv(gym.Env):
    """
    Wraps the pygame game as a Gymnasium environment.
    The RL agent interacts here instead of directly with main.py.
    """

    def __init__(self, render_mode=None):
        super().__init__()
        self.render_mode = render_mode

        # --- Define what the agent can observe ---
        # Option A: raw pixels (screen as image)
        # Option B: hand-crafted game state vector (player pos, velocity, etc.)
        # Start with option B — easier to train on
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(4,), dtype=np.float32
            # e.g. (player_x, player_y, vel_x, vel_y)
        )

        # --- Define what actions the agent can take ---
        # Discrete: 0=nothing, 1=left, 2=right, 3=jump
        self.action_space = spaces.Discrete(4)

        self.game = None

    def reset(self, *, seed=None, options=None):
        super().reset(seed=seed)
        # TODO: reset your game state here
        # self.game = Game(); self.game.load()
        observation = self._get_obs()
        return observation, {}

    def step(self, action):
        # TODO: apply action to the game
        # e.g. simulate key presses based on action index

        # TODO: advance the game one frame
        # self.game.update()

        observation = self._get_obs()
        reward = self._get_reward()
        terminated = self._is_done()
        truncated = False

        return observation, reward, terminated, truncated, {}

    def _get_obs(self):
        # TODO: return the current game state as a numpy array
        return np.zeros(4, dtype=np.float32)

    def _get_reward(self):
        # TODO: define what good behavior looks like
        return 0.0

    def _is_done(self):
        # TODO: True when episode ends (death, goal reached, etc.)
        return False

    def render(self):
        pass

    def close(self):
        pygame.quit()
