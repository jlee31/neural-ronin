import pygame

def _melee_hit_rect(body, flip, width, height, extend):
    w, h = width, height
    if flip:
        left = body.left - w + extend
    else:
        left = body.right - extend
    top = body.centery - h // 2
    return pygame.Rect(left, top, w, h)

def attack_hit_rect(entity):
    """Hitbox in front of the entity during active attack frames, else None."""
    if not entity.attacking or entity.action != "attack":
        return None
    anim = entity.animation
    if anim is None or anim.frame not in entity.ATTACK_HIT_FRAMES:
        return None
    return _melee_hit_rect(
        entity.rect, entity.flip[0], *entity.ATTACK_HITBOX, entity.ATTACK_EXTEND
    )

def try_enemy_attack_hit(enemy, player):
    hit_rect = attack_hit_rect(enemy)
    if hit_rect is None:
        return
    if enemy.last_hit_player_swing == enemy.attack_swing_id:
        return
    if not (hit_rect.colliderect(player.rect) or enemy.rect.colliderect(player.rect)):
        return

    # mark the swing resolved even if take_damage no-ops (i-frames)
    player.take_damage(enemy.ATTACK_DAMAGE, source_x=enemy.center[0])
    enemy.last_hit_player_swing = enemy.attack_swing_id

def apply_player_attack_hits(player, enemies):
    """Damage enemies in the swing hitbox, once per swing each. Returns kill count."""
    hit_rect = attack_hit_rect(player)
    if hit_rect is None:
        return 0

    swing_id = player.attack_swing_id
    kills = 0
    for enemy in enemies:
        if not enemy.alive:
            continue
        if enemy.last_hit_by_player_swing == swing_id:
            continue
        # body overlap counts too so stacked / overhead hits land
        if not (hit_rect.colliderect(enemy.rect) or player.rect.colliderect(enemy.rect)):
            continue
        if enemy.take_damage_from_player(1, player.center[0]):
            enemy.last_hit_by_player_swing = swing_id
            if not enemy.alive:
                kills += 1
    return kills
