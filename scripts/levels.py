"""Level definitions and off-screen enemy spawn placement."""

from scripts.SETTINGS import DISPLAY_WIDTH

FLOOR_Y = 17 * 32 - 30
OFFSCREEN_MARGIN = 80
SPAWN_SPREAD = 56

# Each entry is one level. Levels beyond this list scale from the last template.
LEVELS = [
    {
        "enemy_count": 2,
        "max_health": 2,
        "run_speed": 70,
        "melee_cooldown": 1.35,
        "respawn_sec": 4.0,
        "kills_to_advance": 3,
        "score_per_kill": 100,
    },
    {
        "enemy_count": 3,
        "max_health": 2,
        "run_speed": 82,
        "melee_cooldown": 1.15,
        "respawn_sec": 3.5,
        "kills_to_advance": 5,
        "score_per_kill": 120,
    },
    {
        "enemy_count": 3,
        "max_health": 3,
        "run_speed": 94,
        "melee_cooldown": 1.0,
        "respawn_sec": 3.0,
        "kills_to_advance": 6,
        "score_per_kill": 150,
    },
    {
        "enemy_count": 4,
        "max_health": 3,
        "run_speed": 106,
        "melee_cooldown": 0.88,
        "respawn_sec": 2.5,
        "kills_to_advance": 8,
        "score_per_kill": 180,
    },
    {
        "enemy_count": 4,
        "max_health": 4,
        "run_speed": 118,
        "melee_cooldown": 0.72,
        "respawn_sec": 2.0,
        "kills_to_advance": 10,
        "score_per_kill": 220,
    },
]


def get_level_config(level: int) -> dict:
    """Return tunables for level 1, 2, 3, … (scales past defined LEVELS)."""
    level = max(1, level)
    if level <= len(LEVELS):
        cfg = dict(LEVELS[level - 1])
    else:
        cfg = dict(LEVELS[-1])
        extra = level - len(LEVELS)
        cfg["enemy_count"] = min(6, cfg["enemy_count"] + extra // 2)
        cfg["max_health"] = cfg["max_health"] + extra // 2
        cfg["run_speed"] = cfg["run_speed"] + extra * 6
        cfg["melee_cooldown"] = max(0.45, cfg["melee_cooldown"] - extra * 0.06)
        cfg["respawn_sec"] = max(1.2, cfg["respawn_sec"] - extra * 0.15)
        cfg["kills_to_advance"] = cfg["kills_to_advance"] + extra * 2
        cfg["score_per_kill"] = cfg["score_per_kill"] + extra * 25
    cfg["level"] = level
    return cfg


def spawn_positions_offscreen(player_x, camera_x, map_w, count, floor_y=FLOOR_Y):
    """
    Place enemies outside the camera, on the side away from the player.
    """
    cam_left = camera_x
    cam_right = camera_x + DISPLAY_WIDTH
    spawn_on_right = player_x >= (cam_left + cam_right) * 0.5

    positions = []
    for i in range(count):
        if spawn_on_right:
            x = cam_right + OFFSCREEN_MARGIN + i * SPAWN_SPREAD
        else:
            x = cam_left - OFFSCREEN_MARGIN - i * SPAWN_SPREAD
        x = max(40, min(map_w - 48, x))
        positions.append((x, floor_y))

    return positions
