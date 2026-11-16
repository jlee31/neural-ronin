from scripts.SETTINGS import DISPLAY_WIDTH

FLOOR_Y = 17 * 32 - 30
OFFSCREEN_MARGIN = 80
EDGE_PAD = 48        # keep spawns off the map edges
MIN_GAP = 34         # min spacing between spawn points

# one entry per level; levels past the end scale from the last one
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


def get_level_config(level):
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
    Random off-camera spawn points, preferring the side away from the player.
    Falls back to the other side, then to any legal x.
    """
    cam_left = camera_x
    cam_right = camera_x + DISPLAY_WIDTH
    zones = {
        "left": (EDGE_PAD, cam_left - OFFSCREEN_MARGIN),
        "right": (cam_right + OFFSCREEN_MARGIN, map_w - EDGE_PAD),
    }
    zones = {k: (lo, hi) for k, (lo, hi) in zones.items() if hi - lo >= MIN_GAP}
    preferred = "right" if player_x < (cam_left + cam_right) / 2 else "left"
    order = [z for z in (preferred, "left", "right") if z in zones]
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
