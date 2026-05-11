import pygame

import scripts.pygpen as pp


class Game(pp.PygpenGame):
    def load(self):
        pp.init(
            (1280, 720),
            caption='neural-ronin',
        )
        self.display = pygame.Surface((640, 360))

    def update(self):
        self.display.fill((20, 20, 28))

        self.e['Renderer'].cycle({'default': self.display})

        window = self.e['Window']
        scaled = pygame.transform.scale(self.display, window.screen.get_size())
        window.screen.blit(scaled, (0, 0))
        window.cycle()


Game().run()
