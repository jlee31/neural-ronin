import scripts.pygpen as pp

GRAVITY = 500
JUMP_VEL = 400
RUN_SPEED = 130
MAX_FALL = 330
MAX_JUMPS = 2            # ground jump + 1 air jump
COYOTE_TIME = 0.08
JUMP_BUFFER = 0.10
ATTACK_COOLDOWN = 0.45
DASH_SPEED = 260
DASH_SEC = 0.12          # also the dash i-frame window
DASH_COOLDOWN = 0.80
INVULN_TIME = 0.60       # i-frames after taking a hit
KNOCKBACK_X = 160
KNOCKBACK_Y = -120
MAX_HEALTH = 8


class Player(pp.PhysicsEntity):
    # read by combat.attack_hit_rect
    ATTACK_HIT_FRAMES = (2, 3)   # attack anim frames where the sword connects
    ATTACK_HITBOX = (24, 20)
    ATTACK_EXTEND = 2            # horizontal overlap from body edge into the hitbox

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.acceleration[1] = GRAVITY
        self.velocity_caps = [400, MAX_FALL]

        self.air_time = 0
        self.jumps_left = MAX_JUMPS
        self.coyote = 0
        self.jump_buf = 0
        self.was_airborne = False

        self.health = MAX_HEALTH
        self.invuln = 0
        self.attacking = False
        self.attack_cd = 0
        self.dash_time = 0
        self.dash_cd = 0
        self.dash_dir = 1
        self.attack_swing_id = 0  # bumped each swing so an enemy is hit once per swing
        self.dying = False
        self.done = False         # death anim finished

        # animations advance one frame at a time off the sim clock
        self.anim_last_tick_ms = self.e['Game'].sim_time_ms

    @property
    def alive(self):
        return not self.done

    @property
    def dashing(self):
        return self.dash_time > 0

    def set_action(self, action, force=False):
        changed = force or self.action != action
        super().set_action(action, force=force)
        if changed:
            self.anim_last_tick_ms = self.e['Game'].sim_time_ms

    def _tick_animation(self):
        a = self.animation
        if a is None:
            return
        frame_idx = min(len(a.images) - 1, a.frame)
        cooldown_ms = int(a.config['frames'][frame_idx] * 1000)
        now = self.e['Game'].sim_time_ms
        if now - self.anim_last_tick_ms < cooldown_ms:
            return
        self.anim_last_tick_ms = now
        if a.frame >= len(a.images) - 1:
            if a.config.get('loop', True):
                a.frame = 0
            else:
                a.finished = True
        else:
            a.frame += 1

    def take_damage(self, amount, source_x=None):
        if self.invuln > 0 or self.dashing or self.health <= 0:
            return False
        self.health = max(0, self.health - amount)
        self.invuln = INVULN_TIME
        self.attacking = False

        self.e["Game"].hit_vfx.spawn_player_hit(self.center, source_x=source_x)

        if source_x is not None:
            sign = 1 if source_x < self.pos[0] else -1
        else:
            sign = 1 if self.flip[0] else -1
        self.velocity[0] = KNOCKBACK_X * sign
        self.velocity[1] = KNOCKBACK_Y

        if self.health == 0:
            self.dying = True
            self.set_action('death', force=True)
        return True

    def update(self):
        # not calling super().update(): pygpen's animation tick is dt-based and
        # can skip frames, so animation is advanced manually in _tick_animation
        dt = self.e['Game'].dt

        self.attack_cd = max(0, self.attack_cd - dt)
        self.dash_cd = max(0, self.dash_cd - dt)
        self.invuln = max(0, self.invuln - dt)
        self.coyote = max(0, self.coyote - dt)
        self.jump_buf = max(0, self.jump_buf - dt)

        if self.dying:
            self.velocity[0] *= 0.85
            self.physics_update(self.e['Game'].physics_map)
            if self.animation and self.animation.finished:
                self.done = True
            self._tick_animation()
            return

        inp = self.e['Game'].input_source

        if inp.pressed('dash') and not self.attacking and not self.dashing and self.dash_cd == 0:
            self.dash_time = DASH_SEC
            self.dash_cd = DASH_COOLDOWN
            held = inp.holding('right') - inp.holding('left')
            self.dash_dir = held if held != 0 else (-1 if self.flip[0] else 1)
            self.flip[0] = self.dash_dir < 0

        locked = self.attacking or self.dashing
        dx = 0 if locked else inp.holding('right') - inp.holding('left')

        if inp.pressed('jump') and not locked:
            self.jump_buf = JUMP_BUFFER

        if inp.pressed('attack') and not locked and self.attack_cd == 0:
            self.attacking = True
            self.attack_swing_id += 1
            self.attack_cd = ATTACK_COOLDOWN
            self.set_action('attack', force=True)

        if self.dashing:
            self.dash_time -= dt
            self.velocity[0] = DASH_SPEED * self.dash_dir
            # no gravity during a dash so air dashes stay flat
            self.velocity[1] = 0
            self.acceleration[1] = 0
            if self.dash_time <= 0:
                self.acceleration[1] = GRAVITY
        elif not locked:
            self.velocity[0] = dx * RUN_SPEED
            if dx > 0:
                self.flip[0] = False
            elif dx < 0:
                self.flip[0] = True
        else:
            self.velocity[0] *= 0.90

        if self.jump_buf > 0 and not self.dashing and (self.jumps_left > 0 or self.coyote > 0):
            self.velocity[1] = -JUMP_VEL
            self.air_time = 0.1
            self.jump_buf = 0
            self.coyote = 0
            self.jumps_left = max(0, self.jumps_left - 1)

        # variable jump height
        if not inp.holding('jump') and self.velocity[1] < -90:
            self.velocity[1] = -90

        self.physics_update(self.e['Game'].physics_map)

        # on_ground flickers on flat floor because pygame.Rect truncates pos to int,
        # so animation uses air_time > COYOTE_TIME instead
        on_ground = self.collide_directions['down']
        airborne = self.air_time > COYOTE_TIME
        if on_ground:
            self.air_time = 0
            self.jumps_left = MAX_JUMPS
            self.coyote = COYOTE_TIME
        elif not self.dashing:
            # a dash zeroes vertical velocity so down-collision can't register; freeze air_time
            self.air_time += dt

        if self.attacking:
            if self.animation and self.animation.finished:
                self.attacking = False
                self.animation.finished = False
            else:
                self.set_action('attack')
        elif self.dashing:
            self.set_action('run')  # no dash sheet, run at dash speed reads fine
        elif airborne:
            if not self.was_airborne:
                self.set_action('jump', force=True)
            else:
                self.set_action('jump')
        elif abs(dx) > 0:
            self.set_action('run')
        else:
            self.set_action('idle')

        self.was_airborne = airborne

        # i-frame blink; set_alpha on RGBA sprites renders as a black box
        if self.invuln > 0:
            self.visible = int(self.invuln * 20) % 2 == 1
        else:
            self.visible = True

        self._tick_animation()
