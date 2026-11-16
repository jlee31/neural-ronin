# neural-ronin roadmap

Two-phase plan: build a real game first, then wire in RL.

---

## Phase 1: Playable platformer

The bar: a samurai you can run/jump around a hand-made level and attack an enemy.

### 1.1 Get the samurai on screen
- [ ] Move `FREE_Samurai 2D Pixel Art v1.2/Sprites/*.png` into `data/images/spritesheets/` (rename to lowercase: `idle.png`, `run.png`, `attack.png`, `hurt.png`)
- [ ] Figure out frame size of each spritesheet (check the sheet, count frames)
- [ ] Create `scripts/entities/player.py` with a `Player(PhysicsEntity)` class
- [ ] Load + render the IDLE animation in `main.py`
- [ ] **Done when:** samurai appears on the black screen, idle-animating

### 1.2 Movement + gravity
- [ ] Set up `data/config/key_config.json` for left/right/jump
- [ ] In `Player.update()`: read input, apply horizontal velocity, gravity, jump impulse
- [ ] Add a single floor tile so he doesn't fall forever
- [ ] Switch animation: idle → run → jump based on state
- [ ] **Done when:** can move + jump, animations swap correctly

### 1.3 Real level
- [ ] Find or make a tileset (16x16 pixel tiles matching samurai art style)
- [ ] Drop it in `data/images/tiles/`
- [ ] Run `level_editor.py`, paint a small level (a few platforms, some walls)
- [ ] Save level to `data/maps/0.json`
- [ ] Load + render the level in `main.py`
- [ ] **Done when:** can move around a real level with collisions

### 1.4 Combat + enemy
- [ ] Add attack action (key press → play attack animation, spawn hitbox)
- [ ] Create `scripts/entities/enemy.py`: basic enemy that walks back and forth
- [ ] Hitbox vs enemy → enemy takes damage / dies
- [ ] Enemy can hurt player on contact (HURT animation)
- [ ] Player has HP, dies when HP=0
- [ ] **Done when:** can defeat an enemy and also be defeated

---

## Phase 2: Make it a real game

Loose list, fill in as the game takes shape:
- [ ] Health bar / UI (`pygpen` has `ui/` helpers)
- [ ] Multiple levels + level transitions
- [ ] Title screen, pause menu
- [ ] Sound effects (footsteps, sword swing, hit, death)
- [ ] Background music
- [ ] Particle effects on hit / jump (`pygpen` has `vfx/sparks`, `vfx/particles`)
- [ ] Death + respawn flow
- [ ] Save game state

---

## Phase 3: Reinforcement learning

The game should already be playable + fun before starting this. RL needs:
- Deterministic frame stepping (no wall-clock dependency in game logic)
- Inspectable game state (player pos/vel, enemy pos, hp, etc. accessible from outside)
- Headless mode (run game without opening a window)

**See [docs/RL_GUIDE.md](../docs/RL_GUIDE.md)** for the env, reward and training details.

### 3.1 Headless game ✅

- [x] Refactor `Game` so it can run without a `Window` (SDL dummy driver)
- [x] Step-mode: `Game.step(actions)` advances exactly one fixed-dt frame
- [x] Seeded RNG, sim-time animation clock, input adapter: all in place

### 3.2 Wire up `rl/env.py` ✅
- [x] `reset()` / `step()` / `build_obs()` with a 17-float feature observation
- [x] shaped reward: damage dealt, kills, damage taken, time cost, death

### 3.3 Train
- [x] `train.py`: PPO on `GameEnv`, 8 parallel workers, eval + checkpoint callbacks
- [x] smoke training confirms the pipeline works
- [ ] Tune from there

---

## Notes

- Use `level_editor.py` whenever level design needs to change: don't hand-edit JSON.
- Keep `Game.update()` free of wall-clock time (`time.time()`, real sleep): use a `dt` argument so RL can step at any rate.
- When in doubt about a `pygpen` feature, look at `scripts/pygpen/__init__.py`: it lists every public class.
