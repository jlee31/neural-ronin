import pygame
import pytmx

import scripts.pygpen as pp

DISPLAY_W, DISPLAY_H = 640, 360
BG_DIR = "assets/feudal-japan/Background"
MAP_PATH = "assets/maps/test.tmx"

# Parallax speeds for each background layer (back → front)
BG_LAYERS = [
    ("1 (5).png", 0.05),  # sky
    ("1 (4).png", 0.15),  # mountains
    ("1 (3).png", 0.28),  # hills / pagodas
    ("1 (2).png", 0.45),  # foreground silhouette
]


class Game(pp.PygpenGame):
    def load(self):
        pp.init((1280, 720), caption='neural-ronin')
        self.display = pygame.Surface((DISPLAY_W, DISPLAY_H))

        self.tmx_map = pytmx.load_pygame(MAP_PATH, pixelalpha=True)

        # Scale each bg layer to display size; keep originals for tiling
        self.backgrounds = []
        for filename, speed in BG_LAYERS:
            raw = pygame.image.load(f"{BG_DIR}/{filename}").convert_alpha()
            scaled = pygame.transform.scale(raw, (DISPLAY_W, DISPLAY_H))
            self.backgrounds.append((scaled, speed))

        # Start camera so the floor (rows 14-16) is visible near the bottom
        map_h_px = self.tmx_map.height * self.tmx_map.tileheight
        self.camera = [0, map_h_px - DISPLAY_H]

    def _draw_backgrounds(self):
        cam_x = self.camera[0]
        for surf, speed in self.backgrounds:
            offset = int(cam_x * speed) % DISPLAY_W
            self.display.blit(surf, (-offset, 0))
            # tile a second copy so there's no gap when scrolling
            self.display.blit(surf, (DISPLAY_W - offset, 0))

    def _draw_map(self):
        tw = self.tmx_map.tilewidth
        th = self.tmx_map.tileheight
        cx, cy = int(self.camera[0]), int(self.camera[1])
        for layer in self.tmx_map.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                for x, y, image in layer.tiles():
                    if image:
                        # Tiled bottom-aligns tiles taller than the grid tile height
                        draw_y = (y + 1) * th - image.get_height() - cy
                        self.display.blit(image, (x * tw - cx, draw_y))

    def update(self):
        # --- camera movement (WASD) ---
        keys = pygame.key.get_pressed()
        speed = 3
        if keys[pygame.K_a]:
            self.camera[0] -= speed
        if keys[pygame.K_d]:
            self.camera[0] += speed
        if keys[pygame.K_w]:
            self.camera[1] -= speed
        if keys[pygame.K_s]:
            self.camera[1] += speed

        self._draw_backgrounds()
        self._draw_map()

        self.e['Renderer'].cycle({'default': self.display})

        window = self.e['Window']
        window.screen.blit(
            pygame.transform.scale(self.display, window.screen.get_size()), (0, 0)
        )
        window.cycle()


Game().run()
