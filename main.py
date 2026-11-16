import os
import random

import pygame
import pytmx

import scripts.pygpen as pp
from scripts.player import Player, MAX_HEALTH
from scripts.tilemap_bridge import TiledPhysicsBridge
from scripts.background import ParallaxBackground
from scripts.SETTINGS import (
    DISPLAY_WIDTH, DISPLAY_HEIGHT, BG_DIR, MAP_PATH, BG_LAYERS, MAP_EDGE_WALLS,
)
from scripts.enemies import Enemy, Golem, EnemyDirector
from scripts.combat import apply_player_attack_hits
from scripts.game_data import load_high_score, save_high_score
from scripts.levels import FLOOR_Y, get_level_config, spawn_positions
from scripts.hud import draw_play_hud, draw_menu, draw_game_over, draw_banner
from scripts.hit_vfx import HitVFX
from scripts.input_adapter import PygameInputSource, ScriptedInputSource

SPAWN_POS = (200, FLOOR_Y)
CAMERA_LERP = 0.10
SIM_DT = 1.0 / 60.0  # fixed timestep for headless mode

BANNER_SEC = 2.0
WAVE_BREAK_SEC = 2.0
LEVEL_BREAK_SEC = 3.0
WAVE_CLEAR_BONUS = 50
LEVEL_CLEAR_BONUS = 150
LEVEL_CLEAR_HEAL = 2

STATE_MENU = "menu"
STATE_PLAYING = "playing"
STATE_GAME_OVER = "game_over"

# must match config/key_config.json
INPUT_KEYS = ("left", "right", "jump", "attack", "dash", "confirm", "menu")


class Game(pp.PygpenGame):
    """
    Live play:  Game().run()
    Headless:   g = Game(headless=True, seed=42); g.load(); g.reset(); g.step({"right": True})

    Headless mode uses the SDL dummy video driver, a fixed 60Hz timestep, a
    ScriptedInputSource for input, and a sim clock (sim_time_ms) instead of
    pygame.time.get_ticks() so runs are reproducible.
    """

    def __init__(self, headless=False, seed=None):
        super().__init__()
        self.headless = headless
        self.seed = seed
        # sim clock kept as float seconds; int ms per tick would truncate 0.667ms every tick
        self.sim_time_ms = 0
        self._sim_time_s = 0.0
        self.dt = 0.0
        self.rng = random.Random(seed)
        self.input_source = None

    def load(self):
        if self.headless and "SDL_VIDEODRIVER" not in os.environ:
            os.environ["SDL_VIDEODRIVER"] = "dummy"

        pp.init(
            (1280, 720),
            caption="neural-ronin",
            entity_path="config/entities",
            input_path="config/key_config.json",
        )

        self.display = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        self.tmx_map = pytmx.load_pygame(MAP_PATH, pixelalpha=True)
        self.physics_map = TiledPhysicsBridge(self.tmx_map)
        self.background = ParallaxBackground((DISPLAY_WIDTH, DISPLAY_HEIGHT), BG_DIR, BG_LAYERS)

        self.map_w = self.tmx_map.width * self.tmx_map.tilewidth
        self.map_h = self.tmx_map.height * self.tmx_map.tileheight
        self.camera = [0.0, float(self.map_h - DISPLAY_HEIGHT)]

        self.high_score = load_high_score()
        self.state = STATE_MENU
        self.score = 0
        self.is_new_record = False
        self.level = 1
        self.wave = 1
        self.phase = "fighting"  # fighting | wave_break | level_break
        self.phase_timer = 0.0
        self.level_cfg = get_level_config(1)
        self.banner_text = ""
        self.banner_time = 0.0
        self.player = None
        self.enemies = []
        self.director = None
        # separate rng so particles don't affect gameplay randomness; off in headless
        self.hit_vfx = HitVFX(rng=random.Random(self.seed), enabled=not self.headless)

        if self.headless:
            self.input_source = ScriptedInputSource(INPUT_KEYS)
        else:
            self.input_source = PygameInputSource(self.e["Input"])

    def reset(self, seed=None):
        if seed is not None:
            self.seed = seed
            self.rng = random.Random(seed)
        self.sim_time_ms = 0
        self._sim_time_s = 0.0
        self.input_source.clear()
        self.state = STATE_PLAYING
        self.start_run()

    def step(self, actions):
        assert self.headless, "step() is for headless mode only"
        self.input_source.set_actions(actions)
        self._tick(SIM_DT)

    def start_run(self):
        self.score = 0
        self.level = 1
        self.level_cfg = get_level_config(self.level)
        self.wave = 1
        self.phase = "fighting"
        self.phase_timer = 0.0
        self.player = Player("player", SPAWN_POS)
        self._snap_camera_to_player()
        self.hit_vfx.clear()
        self._spawn_wave()
        self._set_banner(f"LEVEL {self.level}")

    def _snap_camera_to_player(self):
        self.camera[0] = max(
            0,
            min(self.map_w - DISPLAY_WIDTH, self.player.center[0] - DISPLAY_WIDTH / 2),
        )

    def _set_banner(self, text):
        self.banner_text = text
        self.banner_time = BANNER_SEC

    def _spawn_wave(self):
        roster = [Enemy] * self.level_cfg["enemy_count"] + [Golem] * self.level_cfg["golem_count"]
        positions = spawn_positions(
            self.player.center[0],
            self.camera[0],
            self.map_w,
            len(roster),
            self.rng,
        )
        self.director = EnemyDirector(self.level_cfg["max_attackers"])
        self.enemies = [
            cls(pos, level_cfg=self.level_cfg, director=self.director, uid=i)
            for i, (cls, pos) in enumerate(zip(roster, positions))
        ]
        for enemy in self.enemies:
            self.hit_vfx.spawn_burst(enemy.center)

    def _advance_level(self):
        self.level += 1
        self.level_cfg = get_level_config(self.level)
        self.wave = 1
        self._spawn_wave()
        self._set_banner(f"LEVEL {self.level}")

    def _update_wave_flow(self, dt):
        if self.phase == "fighting":
            if self.enemies and all(not e.alive for e in self.enemies):
                if self.wave >= self.level_cfg["wave_count"]:
                    self.phase = "level_break"
                    self.phase_timer = LEVEL_BREAK_SEC
                    self.score += LEVEL_CLEAR_BONUS
                    self.player.health = min(
                        MAX_HEALTH, self.player.health + LEVEL_CLEAR_HEAL
                    )
                    self._set_banner(f"LEVEL {self.level} CLEAR")
                else:
                    self.phase = "wave_break"
                    self.phase_timer = WAVE_BREAK_SEC
                    self.score += WAVE_CLEAR_BONUS
                    self._set_banner("WAVE CLEAR")
        else:
            self.phase_timer -= dt
            if self.phase_timer <= 0:
                if self.phase == "wave_break":
                    self.wave += 1
                    self._spawn_wave()
                    self._set_banner(f"WAVE {self.wave}/{self.level_cfg['wave_count']}")
                else:
                    self._advance_level()
                self.phase = "fighting"

    def _update_camera(self):
        target_x = self.player.center[0] - DISPLAY_WIDTH / 2
        target_y = self.player.center[1] - DISPLAY_HEIGHT / 2
        self.camera[0] += (target_x - self.camera[0]) * CAMERA_LERP
        self.camera[1] += (target_y - self.camera[1]) * CAMERA_LERP
        self.camera[0] = max(0, min(self.map_w - DISPLAY_WIDTH, self.camera[0]))
        self.camera[1] = max(0, min(self.map_h - DISPLAY_HEIGHT, self.camera[1]))

    def _draw_world(self):
        offset = (int(self.camera[0]), int(self.camera[1]))
        self.background.draw(self.display, self.camera[0])
        self.physics_map.draw(self.display, self.tmx_map, self.camera)
        for enemy in self.enemies:
            if enemy.alive or enemy.state == "dying":
                enemy.render(self.display, offset=offset)
        self.player.render(self.display, offset=offset)
        self.hit_vfx.render(self.display, offset=offset)

    def _tick(self, dt):
        self.dt = dt
        # pygpen physics reads Window.dt, which only window.cycle() updates (never in headless)
        self.e["Window"].dt = dt
        self._sim_time_s += dt
        self.sim_time_ms = int(self._sim_time_s * 1000)

        if self.state == STATE_MENU:
            if self.input_source.pressed("confirm"):
                self.start_run()
                self.state = STATE_PLAYING
        elif self.state == STATE_PLAYING:
            self._tick_playing(dt)
        elif self.state == STATE_GAME_OVER:
            if self.input_source.pressed("confirm"):
                self.start_run()
                self.state = STATE_PLAYING
            elif self.input_source.pressed("menu"):
                self.state = STATE_MENU
            self.hit_vfx.update(dt)

    def _clamp_to_map(self, entity):
        entity.pos[0] = max(0.0, min(entity.pos[0], self.map_w - entity.size[0]))

    def _tick_playing(self, dt):
        self.player.update()
        if MAP_EDGE_WALLS:
            self._clamp_to_map(self.player)
        # fell off the map: no floor to play the death anim on, end the run now
        if self.player.alive and self.player.center[1] > self.map_h:
            self.player.health = 0
            self.player.done = True
        for enemy in self.enemies:
            enemy.update(self.player, self.enemies)
            if MAP_EDGE_WALLS:
                self._clamp_to_map(enemy)

        kills = apply_player_attack_hits(self.player, self.enemies)
        if kills:
            self.score += kills * self.level_cfg["score_per_kill"]

        self.hit_vfx.update(dt)
        self._update_wave_flow(dt)
        self._update_camera()

        if self.banner_time > 0:
            self.banner_time = max(0.0, self.banner_time - dt)

        if not self.player.alive:
            old_high = self.high_score
            if self.score > self.high_score and not self.headless:
                self.high_score = self.score
                save_high_score(self.high_score)
            self.is_new_record = self.score > old_high and self.score > 0
            self.state = STATE_GAME_OVER

    def update(self):
        self._tick(self.e["Window"].dt)

        if self.state == STATE_MENU:
            self.background.draw(self.display, 0)
            draw_menu(self.display, self.high_score)
        elif self.state == STATE_PLAYING:
            self._draw_world()
            draw_play_hud(
                self.display,
                self.score,
                self.high_score,
                self.player.health,
                MAX_HEALTH,
                self.level,
                self.wave,
                self.level_cfg["wave_count"],
                sum(1 for e in self.enemies if e.alive),
            )
            if self.banner_time > 0:
                draw_banner(self.display, self.banner_text, self.banner_time / BANNER_SEC)
        elif self.state == STATE_GAME_OVER:
            self._draw_world()
            draw_game_over(
                self.display,
                self.score,
                self.high_score,
                self.is_new_record,
                self.level,
            )

        self.e["Renderer"].cycle({"default": self.display})
        window = self.e["Window"]
        window.screen.blit(
            pygame.transform.scale(self.display, window.screen.get_size()),
            (0, 0),
        )
        window.cycle()


if __name__ == "__main__":
    Game().run()
