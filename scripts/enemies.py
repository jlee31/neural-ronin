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
# Jumping to reach an elevated player.
JUMP_VEL = -300           # upward impulse (weaker than player's -400)
JUMP_RANGE_X = 100        # horizontal distance at which the jump is worth attempting
JUMP_MIN_HEIGHT = 48      # player must be at least this many px above to trigger
JUMP_COOLDOWN = 1.6       # seconds between jumps

# AI feel tunables.
SPAWN_IN_SEC = 0.6        # materialize time: hidden, then blinking in, before acting
STANDOFF_DIST = 70        # px enemies without an attack token keep from the player
CLOSE_DIST = 28           # px the token holder closes to (inside ATTACK_RANGE_X)
TOKEN_REQUEST_DIST = 120  # only ask the director for a token within this range
FACING_DEADZONE = 12      # px past center before the enemy turns around
WINDUP_SEC = 0.35         # frozen telegraph before the swing anim starts
RECOVER_SEC = 0.5         # back-off time after a swing
RECOVER_SPEED_MULT = 0.5
ACCEL_LERP = 10.0         # per-second velocity lerp toward the target speed
SEPARATION_DIST = 16      # px between enemy centers before they push apart
SEPARATION_PUSH = 40      # px/s added to fan out stacked enemies
SPEED_JITTER = (0.9, 1.1)  # per-spawn run-speed multiplier range


class EnemyDirector:
    """Caps how many enemies may press the attack at once (aggression tokens)."""

    def __init__(self, max_attackers):
        self.max_attackers = max_attackers
        self.holders = set()  # enemy uids

    def request(self, enemy):
        if enemy.uid in self.holders:
            return True
        if len(self.holders) < self.max_attackers:
            self.holders.add(enemy.uid)
            return True
        return False

    def release(self, enemy):
        self.holders.discard(enemy.uid)


class Enemy(pp.PhysicsEntity):
    """
    State machine: spawning -> pursue -> windup -> swing -> recover -> pursue,
    interrupted by hurt (player hit landed) and dying (health reached 0).

    Only aggression-token holders (EnemyDirector) may enter windup; the rest
    hold a standoff distance so the player is never blob-rushed.

    Subclasses override the class attributes below to make new enemy types;
    level configs are Bringer-tuned, so the scales adapt them per type.
    """

    ENTITY_ID = "dummy_enemy"
    FLIP_DRAW_SHIFT = 71      # px the sprite jumps when mirrored (off-center art)
    SPEED_SCALE = 1.0         # multiplier on the level config's run_speed
    HEALTH_BONUS = 0          # added to the level config's max_health
    COOLDOWN_SCALE = 1.0      # multiplier on the level config's melee_cooldown
    KNOCKBACK_MULT = 1.0      # how far player hits shove this enemy
    STAGGERS = True           # False = poise: hits never interrupt the current action
    CAN_JUMP = True
    WINDUP = WINDUP_SEC
    ATTACK_HIT_FRAMES = (4, 5, 6)  # 0-based `attack` anim frames that can connect
    ATTACK_HITBOX = (28, 24)       # melee hitbox in front of the body (width, height)
    ATTACK_EXTEND = 4              # horizontal overlap from body edge into the swing arc
    ATTACK_DAMAGE = 1

    def __init__(self, pos, level_cfg=None, director=None, uid=0):
        super().__init__(self.ENTITY_ID, list(pos))
        self.director = director if director is not None else EnemyDirector(1)
        self.uid = uid
        self.acceleration[1] = GRAVITY
        self.velocity_caps = [350, MAX_FALL]

        self.max_health = MAX_HEALTH + self.HEALTH_BONUS
        self.run_speed = RUN_SPEED * self.SPEED_SCALE
        self.melee_cooldown_base = MELEE_COOLDOWN * self.COOLDOWN_SCALE
        self.invuln = 0.0
        self.melee_cd = 0.0
        if level_cfg:
            self.apply_level_config(level_cfg)
        self.health = self.max_health
        self.alive = True
        self.state = "spawning"
        self.state_time = 0.0
        self.visible = False
        self.token = False
        self.speed_mult = self._draw_speed_mult()
        self.last_hit_by_player_swing = -1
        self.attack_swing_id = 0
        self.last_hit_player_swing = -1
        self.jump_cd = 0.0
        self.velocity = [0.0, 0.0]
        self.anim_last_tick_ms = self.e["Game"].sim_time_ms

    @property
    def attacking(self):
        # combat.py and rl/env.py read this; windup counts so the telegraph is observable
        return self.state in ("windup", "swing")

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
            x -= self.FLIP_DRAW_SHIFT
        return (x, y)

    def _draw_speed_mult(self):
        lo, hi = SPEED_JITTER
        return lo + (hi - lo) * self.e["Game"].rng.random()

    def apply_level_config(self, cfg):
        self.max_health = cfg["max_health"] + self.HEALTH_BONUS
        self.run_speed = cfg["run_speed"] * self.SPEED_SCALE
        self.melee_cooldown_base = cfg["melee_cooldown"] * self.COOLDOWN_SCALE

    # ------------------------------------------------------------------ state helpers
    def _enter_state(self, state):
        self.state = state
        self.state_time = 0.0

    def _release_token(self):
        self.director.release(self)
        self.token = False

    def take_damage_from_player(self, amount, source_x):
        if not self.alive or self.invuln > 0:
            return False
        self.health = max(0, self.health - amount)
        self.invuln = INVULN_AFTER_HIT
        sign = 1 if source_x < self.pos[0] else -1
        self.velocity[0] = KNOCKBACK_X * sign * self.KNOCKBACK_MULT
        self.velocity[1] = KNOCKBACK_Y * self.KNOCKBACK_MULT
        if self.health <= 0:
            self._release_token()
            self.alive = False
            self._enter_state("dying")
            self.set_action("death", force=True)
            self.anim_last_tick_ms = self.e["Game"].sim_time_ms
            return True
        if self.STAGGERS:
            # play the hurt animation and lock out new attacks until it finishes
            self._release_token()
            self._enter_state("hurt")
            self.set_action("hurt", force=True)
            self.anim_last_tick_ms = self.e["Game"].sim_time_ms
        # else: poise — the hit lands (damage, blink) but nothing is interrupted
        return True

    def _face_player(self, player):
        # deadzone stops the flip-flicker (and the 71px flip-offset jump)
        # when the player hovers directly above the enemy's center
        diff = player.center[0] - self.center[0]
        if abs(diff) > FACING_DEADZONE:
            self.flip[0] = diff < 0

    def _in_attack_range(self, player):
        return (
            abs(player.center[0] - self.center[0]) <= ATTACK_RANGE_X
            and abs(player.center[1] - self.center[1]) <= ATTACK_RANGE_Y
        )

    def _tick_animation_step(self):
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

    def _anim_finished(self):
        return self.animation is not None and self.animation.finished

    def _separation_push(self, enemies):
        push = 0.0
        for other in enemies:
            if other is self or not other.alive:
                continue
            if abs(self.center[1] - other.center[1]) > 24:
                continue
            d = self.center[0] - other.center[0]
            if abs(d) < SEPARATION_DIST:
                if d != 0:
                    push += SEPARATION_PUSH if d > 0 else -SEPARATION_PUSH
                else:
                    # perfectly stacked: break the tie deterministically
                    push += SEPARATION_PUSH if self.uid > other.uid else -SEPARATION_PUSH
        return push

    def _approach(self, target_vx, dt):
        # accelerate toward the target speed instead of snapping — reads as weight
        self.velocity[0] += (target_vx - self.velocity[0]) * min(1.0, ACCEL_LERP * dt)

    # ------------------------------------------------------------------ per-state updates
    def _update_pursue(self, player, enemies, dt):
        target_vx = 0.0
        player_active = player.alive and not player.dying

        if player_active:
            self._face_player(player)
            diff = player.center[0] - self.center[0]
            dist = abs(diff)

            # ask for an attack token once we're near enough to matter
            if not self.token and self.melee_cd <= 0 and dist <= TOKEN_REQUEST_DIST:
                self.token = self.director.request(self)

            # token holder presses in; everyone else holds a standoff ring
            desired = CLOSE_DIST if self.token else STANDOFF_DIST
            if dist > desired:
                direction = 1 if diff > 0 else -1
                target_vx = direction * self.run_speed * self.speed_mult

            if self.token and self.melee_cd <= 0 and self._in_attack_range(player):
                self._enter_state("windup")
                self.attack_swing_id += 1
                self.last_hit_player_swing = -1
                self.velocity[0] = 0
                self.anim_last_tick_ms = self.e["Game"].sim_time_ms
                self.set_action("attack", force=True)
                return

            # Jump when the player is elevated and we're close enough horizontally.
            if (
                self.CAN_JUMP
                and self.jump_cd <= 0
                and self.collide_directions.get("down", False)
                and dist <= JUMP_RANGE_X
                and (self.center[1] - player.center[1]) >= JUMP_MIN_HEIGHT
            ):
                self.velocity[1] = JUMP_VEL
                self.jump_cd = JUMP_COOLDOWN

        target_vx += self._separation_push(enemies)
        self._approach(target_vx, dt)
        self.physics_update(self.e["Game"].physics_map)

        if abs(self.velocity[0]) > 8:
            self.set_action("run")
        else:
            self.set_action("idle")
        if self.source == "animations" and self.animation:
            self.animation.update(dt)

    def _update_windup(self):
        # frozen telegraph: hold attack frame 0, then let the swing anim run
        self.velocity[0] *= 0.85
        self.physics_update(self.e["Game"].physics_map)
        if self.state_time >= self.WINDUP:
            self._enter_state("swing")
            self.anim_last_tick_ms = self.e["Game"].sim_time_ms

    def _update_swing(self, player):
        self.velocity[0] *= 0.85
        self.physics_update(self.e["Game"].physics_map)
        self._tick_animation_step()
        try_enemy_attack_hit(self, player)
        if self._anim_finished():
            self.animation.finished = False
            self.melee_cd = self.melee_cooldown_base
            self._release_token()
            self._enter_state("recover")

    def _update_recover(self, player, enemies, dt):
        # back off to reset spacing — keeps facing the player while retreating
        target_vx = 0.0
        if player.alive and not player.dying:
            self._face_player(player)
            away = -1 if player.center[0] > self.center[0] else 1
            target_vx = away * self.run_speed * RECOVER_SPEED_MULT
        target_vx += self._separation_push(enemies)
        self._approach(target_vx, dt)
        self.physics_update(self.e["Game"].physics_map)

        self.set_action("run" if abs(self.velocity[0]) > 8 else "idle")
        if self.source == "animations" and self.animation:
            self.animation.update(dt)
        if self.state_time >= RECOVER_SEC:
            self._enter_state("pursue")

    def _update_hurt(self):
        # knockback decays, no input, wait for hurt anim to finish
        self.velocity[0] *= 0.85
        self.physics_update(self.e["Game"].physics_map)
        self._tick_animation_step()
        if self._anim_finished():
            self.animation.finished = False
            self._enter_state("pursue")

    def _update_spawning(self):
        # materialize: hidden at first, then blink in; gravity settles the body.
        # No actions and no facing changes until fully formed.
        self.velocity[0] = 0.0
        self.physics_update(self.e["Game"].physics_map)
        t = self.state_time
        if t < SPAWN_IN_SEC * 0.4:
            self.visible = False
        else:
            self.visible = int(t * 20) % 2 == 1
        if t >= SPAWN_IN_SEC:
            self.visible = True
            self._enter_state("pursue")

    def _update_dying(self):
        # body settles while the death anim plays, then the sprite hides
        self.velocity[0] *= 0.85
        self.physics_update(self.e["Game"].physics_map)
        self._tick_animation_step()
        if self._anim_finished():
            self.visible = False
            self._enter_state("dead")

    # ------------------------------------------------------------------ update
    def update(self, player, enemies):
        if not self.alive and self.state not in ("dying",):
            return

        dt = self.e["Game"].dt
        self.invuln = max(0.0, self.invuln - dt)
        self.melee_cd = max(0.0, self.melee_cd - dt)
        self.jump_cd = max(0.0, self.jump_cd - dt)
        self.state_time += dt

        if self.state == "dying":
            self._update_dying()
            return
        if self.state == "spawning":
            # handles its own visibility (blink-in) — skip the invuln block below
            self._update_spawning()
            return
        if self.state == "hurt":
            self._update_hurt()
        elif self.state == "windup":
            self._update_windup()
        elif self.state == "swing":
            self._update_swing(player)
        elif self.state == "recover":
            self._update_recover(player, enemies, dt)
        else:
            self._update_pursue(player, enemies, dt)

        if self.invuln > 0:
            self.visible = int(self.invuln * 18) % 2 == 1
        else:
            self.visible = True


class Golem(Enemy):
    """
    Armored tank — the Bringer's opposite. Slow stomp, extra health, a long
    telegraphed slam that hits for 2, and poise: player hits never stagger it
    or interrupt its swing. You dodge the slam; you don't stun-lock it.
    """

    ENTITY_ID = "golem"
    FLIP_DRAW_SHIFT = 0       # golem art is centered in its 64px frame
    SPEED_SCALE = 0.45
    HEALTH_BONUS = 2
    COOLDOWN_SCALE = 1.5
    KNOCKBACK_MULT = 0.25     # barely budges
    STAGGERS = False
    CAN_JUMP = False          # too heavy — camp a platform and it can't reach you
    WINDUP = 0.25             # the 12-frame slam anim is its own telegraph
    ATTACK_HIT_FRAMES = (6, 7, 8)
    ATTACK_HITBOX = (34, 26)
    ATTACK_EXTEND = 6
    ATTACK_DAMAGE = 2
