import scripts.pygpen as pp
from scripts.combat import try_enemy_attack_hit

# Match player-ish platforming so RL / human controls feel comparable.
GRAVITY = 500
RUN_SPEED = 75
MAX_FALL = 330
INVULN_AFTER_HIT = 0.45
MELEE_COOLDOWN = 1.2
MAX_HEALTH = 2
KNOCKBACK_X = 130
KNOCKBACK_Y = -90
# How close before the enemy winds up an attack (not damage range — hitbox handles that).
ATTACK_RANGE_X = 38
ATTACK_RANGE_Y = 30


class DummyEnemy(pp.PhysicsEntity):
    """Chase the player and swing with a real attack animation + hitbox."""

    def __init__(self, pos, spawn_pos=None, level_cfg=None):
        super().__init__("dummy_enemy", list(pos))
        self.spawn_pos = list(spawn_pos if spawn_pos is not None else pos)
        self.acceleration[1] = GRAVITY
        self.velocity_caps = [350, MAX_FALL]

        self.max_health = MAX_HEALTH
        self.run_speed = RUN_SPEED
        self.melee_cooldown_base = MELEE_COOLDOWN
        self.health = MAX_HEALTH
        self.invuln = 0.0
        self.melee_cd = 0.0
        if level_cfg:
            self.apply_level_config(level_cfg)
        self.alive = True
        self.last_hit_by_player_swing = -1
        self.attacking = False
        self.attack_swing_id = 0
        self.last_hit_player_swing = -1
        self.stunned = False
        self.velocity = [0.0, 0.0]
        self.anim_last_tick_ms = self.e["Game"].sim_time_ms

    @property
    def local_offset(self):
        # Character is drawn off-center in the 140-wide Bringer frame (body at
        # x≈12-56). When pygame mirrors the sprite for flip[0]=True the body
        # snaps to x≈84-128, so the visible character jumps 71 px sideways.
        # Compensate by shifting the draw offset the other way when flipped.
        img_offset = self.config[self.source][self.action]['offset']
        entity_offset = self.config['offset']
        x = img_offset[0] + entity_offset[0]
        y = img_offset[1] + entity_offset[1]
        if self.flip[0]:
            x -= 71
        return (x, y)

    def apply_level_config(self, cfg):
        self.max_health = cfg["max_health"]
        self.run_speed = cfg["run_speed"]
        self.melee_cooldown_base = cfg["melee_cooldown"]

    def teleport_to_spawn(self, pos):
        """Move to a new off-screen spawn point (used on respawn)."""
        self.spawn_pos = list(pos)
        self.pos = list(pos)

    def respawn(self):
        self.pos = list(self.spawn_pos)
        self.velocity = [0.0, 0.0]
        self.health = self.max_health
        self.invuln = 0.0
        self.melee_cd = 0.0
        self.alive = True
        self.visible = True
        self.opacity = 255
        self.attacking = False
        self.stunned = False
        self.last_hit_by_player_swing = -1
        self.last_hit_player_swing = -1
        self.anim_last_tick_ms = self.e["Game"].sim_time_ms
        self.set_action("idle", force=True)

    def take_damage_from_player(self, amount, source_x):
        if not self.alive or self.invuln > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invuln = INVULN_AFTER_HIT
        self.attacking = False
        sign = 1 if source_x < self.pos[0] else -1
        self.velocity[0] = KNOCKBACK_X * sign
        self.velocity[1] = KNOCKBACK_Y
        if self.health <= 0:
            self.alive = False
            self.visible = False
            return True
        # play the hurt animation and lock out new attacks until it finishes
        self.stunned = True
        self.set_action("hurt", force=True)
        self.anim_last_tick_ms = self.e["Game"].sim_time_ms
        return True

    def _face_player(self, player):
        if player.center[0] >= self.center[0]:
            self.flip[0] = False
        else:
            self.flip[0] = True

    def _in_attack_range(self, player):
        return (
            abs(player.center[0] - self.center[0]) <= ATTACK_RANGE_X
            and abs(player.center[1] - self.center[1]) <= ATTACK_RANGE_Y
        )

    def _start_attack(self):
        self.attacking = True
        self.attack_swing_id += 1
        self.last_hit_player_swing = -1
        self.velocity[0] = 0
        self.anim_last_tick_ms = self.e["Game"].sim_time_ms
        self.set_action("attack", force=True)

    def _tick_attack_animation(self):
        # Same one-frame-per-tick rule as the player — pygpen's dt-based update can
        # skip past hit frames entirely when dt spikes (Window dt_cap).
        a = self.animation
        if a is None:
            return
        frame_idx = min(len(a.images) - 1, a.frame)
        cooldown_ms = int(a.config["frames"][frame_idx] * 1000)
        now = self.e["Game"].sim_time_ms
        if now - self.anim_last_tick_ms < cooldown_ms:
            return
        self.anim_last_tick_ms = now
        if a.frame >= len(a.images) - 1:
            a.finished = True
        else:
            a.frame += 1

    def update(self, player):
        if not self.alive:
            return

        dt = self.e["Game"].dt
        self.invuln = max(0.0, self.invuln - dt)
        self.melee_cd = max(0.0, self.melee_cd - dt)

        if player.alive and not player.dying and not self.stunned:
            self._face_player(player)

        # Decide whether to start a new swing this frame. Blocked while stunned
        # so the hurt animation has to play out before the enemy can swing again.
        if (
            not self.attacking
            and not self.stunned
            and player.alive
            and not player.dying
            and self.melee_cd <= 0
            and self._in_attack_range(player)
        ):
            self._start_attack()

        if self.stunned:
            # knockback decays, no input, wait for hurt anim to finish
            self.velocity[0] *= 0.85
            self.physics_update(self.e["Game"].physics_map)
            self._tick_attack_animation()
            if self.animation and self.animation.finished:
                self.stunned = False
                self.animation.finished = False
        elif self.attacking:
            self.velocity[0] *= 0.85
            self.physics_update(self.e["Game"].physics_map)
            self._tick_attack_animation()
            try_enemy_attack_hit(self, player)
            if self.animation and self.animation.finished:
                self.attacking = False
                self.animation.finished = False
                self.melee_cd = self.melee_cooldown_base
        else:
            dx = 0
            if player.alive and not player.dying:
                diff = player.center[0] - self.center[0]
                if abs(diff) > 4:
                    dx = 1 if diff > 0 else -1

            self.velocity[0] = dx * self.run_speed
            if dx > 0:
                self.flip[0] = False
            elif dx < 0:
                self.flip[0] = True

            self.physics_update(self.e["Game"].physics_map)

            if dx != 0:
                self.set_action("run")
            else:
                self.set_action("idle")

            if self.source == "animations" and self.animation:
                self.animation.update(dt)

        if self.invuln > 0:
            self.visible = int(self.invuln * 18) % 2 == 1
        else:
            self.visible = True
        self.opacity = 255
