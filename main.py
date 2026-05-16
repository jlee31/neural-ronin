import pygame
import pytmx

import scripts.pygpen as pp
from scripts.player import Player
from scripts.tilemap_bridge import TiledPhysicsBridge
from scripts.background import ParallaxBackground
from scripts.SETTINGS import DISPLAY_WIDTH, DISPLAY_HEIGHT, BG_DIR, MAP_PATH, BG_LAYERS

# Spawn above the floor (row 17 on a 32px-tile map), accounting for player height.
SPAWN_POS = (200, 17 * 32 - 30)
CAMERA_LERP = 0.10  # 0 = locked, 1 = snap; lower = smoother follow


class Game(pp.PygpenGame):
    def load(self):
        pp.init((1280, 720),
                caption='neural-ronin',
                entity_path='config/entities',
                input_path='config/key_config.json')

        # internal pixel canvas — scaled up to the window each frame for chunky pixels
        self.display = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT))
        self.tmx_map = pytmx.load_pygame(MAP_PATH, pixelalpha=True)
        self.physics_map = TiledPhysicsBridge(self.tmx_map)
        self.background = ParallaxBackground((DISPLAY_WIDTH, DISPLAY_HEIGHT), BG_DIR, BG_LAYERS)

        # camera clamp bounds, so we never peek past the map edges
        self.map_w = self.tmx_map.width * self.tmx_map.tilewidth
        self.map_h = self.tmx_map.height * self.tmx_map.tileheight
        self.camera = [0.0, float(self.map_h - DISPLAY_HEIGHT)]

        self.reset()

    def reset(self):
        # respawn fresh; called on load and when the player dies
        self.player = Player('player', SPAWN_POS)

    def _update_camera(self):
        # lerp toward a point centered on the player, then clamp inside the map
        target_x = self.player.center[0] - DISPLAY_WIDTH / 2
        target_y = self.player.center[1] - DISPLAY_HEIGHT / 2
        self.camera[0] += (target_x - self.camera[0]) * CAMERA_LERP
        self.camera[1] += (target_y - self.camera[1]) * CAMERA_LERP
        self.camera[0] = max(0, min(self.map_w - DISPLAY_WIDTH, self.camera[0]))
        self.camera[1] = max(0, min(self.map_h - DISPLAY_HEIGHT, self.camera[1]))

    def update(self):
        # respawn the player on death so the loop keeps running
        if not self.player.alive:
            self.reset()

        self.player.update()
        self._update_camera()

        # integer offset avoids jitter when blitting on the pixel canvas
        offset = (int(self.camera[0]), int(self.camera[1]))

        self.background.draw(self.display, self.camera[0])
        self.physics_map.draw(self.display, self.tmx_map, self.camera)
        self.player.render(self.display, offset=offset)

        self.e['Renderer'].cycle({'default': self.display})

        # blit our small pixel canvas scaled up to fill the actual window
        window = self.e['Window']
        window.screen.blit(
            pygame.transform.scale(self.display, window.screen.get_size()), (0, 0)
        )
        window.cycle()


Game().run()
