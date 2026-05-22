# neural ronin

written in pygame

## how to setup : download dependencies

to avoid dependency errors, use a python environment

``` bash
pip install requirements.txt -r
```

### how to play

``` bash
python main.py
```

Controls:

- WASD to Move
- J to attack

### how to do the RL part

those files live within /rl. i used stablebaselines and gymnasium to emulate an environment 

```
python -m rl.train
```

```
python -m rl.train --watch
```

