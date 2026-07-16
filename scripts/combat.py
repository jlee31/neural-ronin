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
    """
    Return a world-space hurtbox in front of the entity during active hit frames, else None.
    Reads the entity's ATTACK_HIT_FRAMES / ATTACK_HITBOX / ATTACK_EXTEND class
    attrs — Player and the Enemy hierarchy all carry them.
    """
    if not entity.attacking or entity.action != "attack":
        return None
    anim = entity.animation
    if anim is None or anim.frame not in entity.ATTACK_HIT_FRAMES:
        return None
    return _melee_hit_rect(
        entity.rect, entity.flip[0], *entity.ATTACK_HITBOX, entity.ATTACK_EXTEND
    )

def try_enemy_attack_hit(enemy, player):
    """Deal damage on active attack frames when the weapon hitbox or bodies overlap."""
    hit_rect = attack_hit_rect(enemy)
    if hit_rect is None:
        return
    if enemy.last_hit_player_swing == enemy.attack_swing_id:
        return
    if not (hit_rect.colliderect(player.rect) or enemy.rect.colliderect(player.rect)):
        return

    # take_damage no-ops during i-frames / after death; mark the swing as resolved
    # regardless so we don't keep re-checking this frame.
    player.take_damage(enemy.ATTACK_DAMAGE, source_x=enemy.center[0])
    enemy.last_hit_player_swing = enemy.attack_swing_id

def apply_player_attack_hits(player, enemies):
    """
    Deal damage to enemies overlapping the current swing hitbox.
    Uses player.attack_swing_id so each swing can hit each enemy at most once.
    Returns how many enemies were killed this frame.
    """
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
        # side-of-body hitbox OR direct body overlap (covers stacked / above-enemy hits)
        if not (hit_rect.colliderect(enemy.rect) or player.rect.colliderect(enemy.rect)):
            continue
        if enemy.take_damage_from_player(1, player.center[0]):
            enemy.last_hit_by_player_swing = swing_id
            if not enemy.alive:
                kills += 1
    return kills
