import pygame


class ParallaxBackground:
    def __init__(self, display_size, bg_dir, layers):
        self.display_w = display_size[0]
        self.surfs = []
        for filename, speed in layers:
            raw = pygame.image.load(f"{bg_dir}/{filename}").convert_alpha()
            scaled = pygame.transform.scale(raw, display_size)
            self.surfs.append((scaled, speed))

    def draw(self, display, cam_x):
        for surf, speed in self.surfs:
            offset = int(cam_x * speed) % self.display_w
            display.blit(surf, (-offset, 0))
            display.blit(surf, (self.display_w - offset, 0))
