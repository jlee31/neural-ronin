import pygame

from scripts.SETTINGS import DISPLAY_WIDTH, DISPLAY_HEIGHT

# Sizes tuned for the 640x360 pixel canvas. Built lazily on first draw because
# pygame.font needs pygame.init() to have run.
_FONTS = None


def _fonts():
    # Lazy-build and cache the three font sizes used across the HUD.
    global _FONTS
    if _FONTS is None:
        _FONTS = {
            "lg": pygame.font.SysFont("consolas", 28, bold=True),
            "md": pygame.font.SysFont("consolas", 18, bold=True),
            "sm": pygame.font.SysFont("consolas", 14),
        }
    return _FONTS


def _shadow(surf, font, text, pos, color=(255, 255, 255)):
    # Draw text twice (black underneath, color on top) for a 1px drop shadow — keeps HUD readable over any background.
    shadow = font.render(text, True, (0, 0, 0))
    main = font.render(text, True, color)
    surf.blit(shadow, (pos[0] + 1, pos[1] + 1))
    surf.blit(main, pos)


def draw_play_hud(
    surf,
    score,
    high_score,
    health,
    max_health,
    level,
    kills_this_level,
    kills_to_advance,
):
    # In-game HUD: score/best top-left, level progress under it, health bar top-right.
    fonts = _fonts()
    _shadow(surf, fonts["md"], f"SCORE {score}", (8, 8))
    _shadow(surf, fonts["sm"], f"BEST {high_score}", (8, 28), (200, 200, 200))
    _shadow(
        surf,
        fonts["sm"],
        f"LV {level}  {kills_this_level}/{kills_to_advance}",
        (8, 46),
        (180, 220, 255),
    )

    bar_w, bar_h = 80, 8
    x = DISPLAY_WIDTH - bar_w - 12
    y = 12
    pygame.draw.rect(surf, (40, 20, 20), (x, y, bar_w, bar_h))
    fill = int(bar_w * max(0, health) / max(1, max_health))
    if fill:
        pygame.draw.rect(surf, (220, 60, 60), (x, y, fill, bar_h))
    pygame.draw.rect(surf, (255, 255, 255), (x, y, bar_w, bar_h), 1)
    _shadow(surf, fonts["sm"], f"{health}/{max_health}", (x, y + 12), (220, 220, 220))


def draw_menu(surf, high_score):
    # Title screen: dim overlay + "NEURAL RONIN" title, high score, and control list.
    fonts = _fonts()
    overlay = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA)
    overlay.fill((12, 14, 22, 200))
    surf.blit(overlay, (0, 0))
    title = "NEURAL RONIN"
    tw = fonts["lg"].size(title)[0]
    _shadow(surf, fonts["lg"], title, ((DISPLAY_WIDTH - tw) // 2, 72), (240, 210, 120))
    _shadow(surf, fonts["md"], f"HIGH SCORE  {high_score}", ((DISPLAY_WIDTH - 200) // 2, 130), (180, 220, 255))
    lines = [
        "ENTER  —  START",
        "A/D    —  MOVE",
        "SPACE  —  JUMP",
        "J      —  ATTACK",
        "CLEAR KILLS TO REACH NEXT LEVEL",
    ]
    y = 200
    for line in lines:
        lw = fonts["sm"].size(line)[0]
        _shadow(surf, fonts["sm"], line, ((DISPLAY_WIDTH - lw) // 2, y), (200, 200, 200))
        y += 22


def draw_level_banner(surf, level, alpha_ratio):
    # Big centered "LEVEL N" flash that fades out as alpha_ratio (1.0 → 0.0) drains.
    fonts = _fonts()
    text = f"LEVEL {level}"
    tw = fonts["lg"].size(text)[0]
    overlay = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, int(90 * alpha_ratio)))
    surf.blit(overlay, (0, 0))
    color = (255, 230, 140)
    _shadow(
        surf,
        fonts["lg"],
        text,
        ((DISPLAY_WIDTH - tw) // 2, DISPLAY_HEIGHT // 2 - 20),
        color,
    )


def draw_game_over(surf, score, high_score, is_new_record, level=1):
    # Death screen: dim overlay + final score/level/best, "NEW HIGH SCORE!" if applicable, and restart prompts.
    overlay = pygame.Surface((DISPLAY_WIDTH, DISPLAY_HEIGHT), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    surf.blit(overlay, (0, 0))

    fonts = _fonts()
    title = "GAME OVER"
    tw = fonts["lg"].size(title)[0]
    _shadow(surf, fonts["lg"], title, ((DISPLAY_WIDTH - tw) // 2, 90), (240, 100, 100))
    _shadow(surf, fonts["md"], f"SCORE  {score}", ((DISPLAY_WIDTH - 140) // 2, 140))
    _shadow(surf, fonts["md"], f"LEVEL  {level}", ((DISPLAY_WIDTH - 140) // 2, 168), (180, 220, 255))
    _shadow(surf, fonts["md"], f"BEST   {high_score}", ((DISPLAY_WIDTH - 140) // 2, 196), (180, 220, 255))
    if is_new_record:
        msg = "NEW HIGH SCORE!"
        mw = fonts["md"].size(msg)[0]
        _shadow(surf, fonts["md"], msg, ((DISPLAY_WIDTH - mw) // 2, 224), (255, 220, 80))
    _shadow(surf, fonts["sm"], "ENTER — TRY AGAIN", ((DISPLAY_WIDTH - 130) // 2, 258))
    _shadow(surf, fonts["sm"], "ESC — MENU", ((DISPLAY_WIDTH - 90) // 2, 280), (180, 180, 180))
