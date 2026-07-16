"""Level definitions and randomized off-camera enemy spawn placement."""

from scripts.SETTINGS import DISPLAY_WIDTH

FLOOR_Y = 17 * 32 - 30
OFFSCREEN_MARGIN = 80
EDGE_PAD = 48        # keep spawns off the map's outer edges
MIN_GAP = 34         # minimum spacing between spawn points

# Each entry is one level. A level is `wave_count` waves of `enemy_count`
# Bringers plus `golem_count` golems; clear every wave to advance. Levels beyond this list scale from
# the last template.
LEVELS = [
    {
        "enemy_count": 2,
        "golem_count": 0,
        "wave_count": 2,
        "max_attackers": 1,
        "max_health": 2,
        "run_speed": 70,
        "melee_cooldown": 1.35,
        "score_per_kill": 100,
    },
    {
        "enemy_count": 3,
        "golem_count": 0,
        "wave_count": 2,
        "max_attackers": 1,
        "max_health": 2,
        "run_speed": 82,
        "melee_cooldown": 1.15,
        "score_per_kill": 120,
    },
    {
        "enemy_count": 3,
        "golem_count": 1,
        "wave_count": 3,
        "max_attackers": 2,
        "max_health": 3,
        "run_speed": 94,
        "melee_cooldown": 1.0,
        "score_per_kill": 150,
    },
    {
        "enemy_count": 4,
        "golem_count": 1,
        "wave_count": 3,
        "max_attackers": 2,
        "max_health": 3,
        "run_speed": 106,
        "melee_cooldown": 0.88,
        "score_per_kill": 180,
    },
    {
        "enemy_count": 4,
        "golem_count": 2,
        "wave_count": 4,
        "max_attackers": 3,
        "max_health": 4,
        "run_speed": 118,
        "melee_cooldown": 0.72,
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
        cfg["wave_count"] = min(6, cfg["wave_count"] + extra // 2)
        cfg["golem_count"] = min(3, cfg["golem_count"] + extra // 3)
        cfg["max_attackers"] = min(4, cfg["max_attackers"] + extra // 4)
        cfg["max_health"] = cfg["max_health"] + extra // 2
        cfg["run_speed"] = cfg["run_speed"] + extra * 6
        cfg["melee_cooldown"] = max(0.45, cfg["melee_cooldown"] - extra * 0.06)
        cfg["score_per_kill"] = cfg["score_per_kill"] + extra * 25
    cfg["level"] = level
    return cfg


def spawn_positions(player_x, camera_x, map_w, count, rng, floor_y=FLOOR_Y):
    """
    Random spawn points outside the camera, preferring the side away from the
    player. Spacing is randomized (no orderly rows). When the preferred side
    has no off-camera room, spawns spill to the other side; as a last resort
    an enemy drops at a random legal x — the spawn-in effect covers that case.
    """
    cam_left = camera_x
    cam_right = camera_x + DISPLAY_WIDTH
    zones = {
        "left": (EDGE_PAD, cam_left - OFFSCREEN_MARGIN),
        "right": (cam_right + OFFSCREEN_MARGIN, map_w - EDGE_PAD),
    }
    # keep only zones wide enough to actually hold a spawn
    zones = {k: (lo, hi) for k, (lo, hi) in zones.items() if hi - lo >= MIN_GAP}
    preferred = "right" if player_x < (cam_left + cam_right) / 2 else "left"
    order = [z for z in (preferred, "left", "right") if z in zones]
    # dedupe while preserving preference order
    order = list(dict.fromkeys(order))

    xs = []
    for _ in range(count):
        placed = False
        for zone in order:
            lo, hi = zones[zone]
            for _attempt in range(8):
                x = rng.uniform(lo, hi)
                if all(abs(x - other) >= MIN_GAP for other in xs):
                    xs.append(x)
                    placed = True
                    break
            if placed:
                break
        if not placed:
            xs.append(rng.uniform(EDGE_PAD, map_w - EDGE_PAD))

    return [(x, floor_y) for x in xs]
