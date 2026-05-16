import pygame
import pytmx

BORDERS = [(-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (0, 0)]


class _PhysTile:
    __slots__ = ('rect', 'physics_type')

    def __init__(self, grid_pos, tile_size, physics_type='solid'):
        self.physics_type = physics_type
        x = grid_pos[0] * tile_size[0]
        y = grid_pos[1] * tile_size[1]
        self.rect = pygame.Rect(x, y, tile_size[0], tile_size[1])


class TiledPhysicsBridge:
    """
    Wraps a pytmx TiledMap and exposes the pygpen Tilemap subset that
    PhysicsEntity.physics_update() needs: nearby_grid_physics(pos).

    Tiles in solid_layers are solid by default. Override per tile in Tiled
    via a custom string property 'physics_type' (solid|dropthrough|rampr|rampl).
    """

    def __init__(self, tmx_map, solid_layers=('Floor',)):
        self.tile_size = (tmx_map.tilewidth, tmx_map.tileheight)
        self._physics_map = {}

        for layer in tmx_map.visible_layers:
            if not isinstance(layer, pytmx.TiledTileLayer):
                continue
            if layer.name not in solid_layers:
                continue
            for x, y, gid in layer:
                if gid == 0:
                    continue
                props = tmx_map.get_tile_properties_by_gid(gid) or {}
                ptype = props.get('physics_type', 'solid')
                self._physics_map[(x, y)] = _PhysTile((x, y), self.tile_size, ptype)

    def draw(self, display, tmx_map, camera):
        tw, th = tmx_map.tilewidth, tmx_map.tileheight
        cx, cy = int(camera[0]), int(camera[1])
        for layer in tmx_map.visible_layers:
            if isinstance(layer, pytmx.TiledTileLayer):
                for x, y, image in layer.tiles():
                    if image:
                        draw_y = (y + 1) * th - image.get_height() - cy
                        display.blit(image, (x * tw - cx, draw_y))

    def nearby_grid_physics(self, pos):
        tw, th = self.tile_size
        gx = int(pos[0]) // tw
        gy = int(pos[1]) // th
        tiles = []
        for dx, dy in BORDERS:
            key = (gx + dx, gy + dy)
            if key in self._physics_map:
                tiles.append(self._physics_map[key])
        return tiles
