# neural ronin

A samurai wave-survival platformer written in pygame, with a headless mode
for training a reinforcement learning agent to play it.

## setup

Use a virtual environment, then:

```bash
pip install -r requirements.txt
```

## play

```bash
python main.py
```

Controls:

- A / D: move
- Space: jump (double jump)
- J: attack
- K: dash (i-frames)
- Enter: start / retry
- Esc: back to menu

Clear every wave to advance to the next level.

## RL

The Gymnasium env and PPO trainer live in `rl/`. Run from the project root:

```bash
python -m rl.train                  # train (2M steps, 8 workers)
python -m rl.train --eval           # headless episode with the saved model
python -m rl.train --watch          # watch the saved model play
tensorboard --logdir rl/logs        # training curves
```

See [docs/RL_GUIDE.md](docs/RL_GUIDE.md) for the observation, action and
reward definitions and how to change them.
