DISPLAY_WIDTH = 640
DISPLAY_HEIGHT = 360

BG_DIR = "assets/feudal-japan/Background"
MAP_PATH = "assets/maps/test.tmx"
# Per-map: invisible walls at x=0 and x=map_w keep everyone in bounds.
# Set False for maps where falling off the sides is part of the design
# (the fall-death check in Game._tick_playing handles that case).
MAP_EDGE_WALLS = True

BG_LAYERS = [
    ("1 (5).png", 0.05),
    ("1 (4).png", 0.15),
    ("1 (3).png", 0.28),
    ("1 (2).png", 0.45),
]

