import scripts.pygpen as pp

# Tunables — adjust these to retune game feel.
GRAVITY = 500            # px/s^2 constant downward pull
JUMP_VEL = 400           # initial upward velocity on jump
RUN_SPEED = 130          # horizontal speed in px/s
MAX_FALL = 330           # terminal fall speed cap
MAX_JUMPS = 2          # 1 ground jump + 1 air jump
COYOTE_TIME = 0.08       # ledge-fall forgiveness window
JUMP_BUFFER = 0.10       # early-press forgiveness window
ATTACK_COOLDOWN = 0.45   # seconds between swings
DASH_SPEED = 260         # horizontal burst speed during a dash (2x run speed)
DASH_SEC = 0.12          # dash duration — also the i-frame window (~180px total)
DASH_COOLDOWN = 0.80     # seconds between dashes
INVULN_TIME = 0.60       # i-frames after a hit
KNOCKBACK_X = 160        # horizontal punch on hit
KNOCKBACK_Y = -120       # small upward pop on hit
MAX_HEALTH = 8


class Player(pp.PhysicsEntity):
    # Melee tuning read by combat.attack_hit_rect — same contract as the
    # ATTACK_* class attrs on the Enemy hierarchy.
    ATTACK_HIT_FRAMES = (2, 3)   # 0-based `attack` anim frames where the sword connects
    ATTACK_HITBOX = (24, 20)     # hitbox in front of the body (width, height)
    ATTACK_EXTEND = 2            # horizontal overlap from body edge into the swing arc

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # gravity is integrated by the engine each frame as y-acceleration
        self.acceleration[1] = GRAVITY
        self.velocity_caps = [400, MAX_FALL]

        # platforming state
        self.air_time = 0
        self.jumps_left = MAX_JUMPS
        self.coyote = 0           # remaining coyote seconds
        self.jump_buf = 0         # remaining buffered-jump seconds
        self.was_airborne = False  # de-noised airborne state, for take-off detection

        # combat state
        self.health = MAX_HEALTH
        self.invuln = 0
        self.attacking = False    # swing in progress — locks movement
        self.attack_cd = 0
        self.dash_time = 0        # >0 = dodge in progress — i-frames + locked movement
        self.dash_cd = 0
        self.dash_dir = 1
        self.attack_swing_id = 0  # incremented each swing — pairs with enemy last_hit tracking
        self.dying = False        # death animation is playing
        self.done = False         # death animation finished — safe to respawn

        # tick-based animation timing (MagesticBrawl-style)
        # avoids pygpen's dt-accumulation sprinting through frames when fps stutters.
        # Uses sim_time_ms (owned by Game) instead of pygame.time.get_ticks() so the
        # animation is reproducible in headless RL mode.
        self.anim_last_tick_ms = self.e['Game'].sim_time_ms

    @property
    def alive(self):
        # "alive" means the run is still ongoing — death anim must finish first
        return not self.done

    @property
    def dashing(self):
        return self.dash_time > 0

    def set_action(self, action, force=False):
        # reset the per-frame timer whenever the action actually changes so the new anim starts fresh
        changed = force or self.action != action
        super().set_action(action, force=force)
        if changed:
            self.anim_last_tick_ms = self.e['Game'].sim_time_ms

    def _tick_animation(self):
        # advance at most ONE frame per call, based on the current frame's configured duration.
        # this is the MagesticBrawl pattern: never sprint through frames on a slow tick.
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
                a.finished = True   # hold last frame
        else:
            a.frame += 1

    def take_damage(self, amount, source_x=None):
        # ignored during i-frames, mid-dash (the dodge!), or once we're already dying
        if self.invuln > 0 or self.dashing or self.health <= 0:
            return False
        self.health = max(0, self.health - amount)
        self.invuln = INVULN_TIME
        self.attacking = False    # cancel any in-progress swing

        self.e["Game"].hit_vfx.spawn_player_hit(self.center, source_x=source_x)

        # knockback away from the hit (fallback: opposite of facing)
        if source_x is not None:
            sign = 1 if source_x < self.pos[0] else -1
        else:
            sign = 1 if self.flip[0] else -1
        self.velocity[0] = KNOCKBACK_X * sign
        self.velocity[1] = KNOCKBACK_Y

        # final hit triggers the death sequence
        if self.health == 0:
            self.dying = True
            self.set_action('death', force=True)
        return True

    def update(self):
        dt = self.e['Game'].dt
        # NOTE: deliberately NOT calling super().update(dt) — that would run pygpen's
        # dt-accumulation animation tick. We drive the animation manually below via
        # _tick_animation() so it can never advance more than one frame per game tick.

        # tick all transient timers in one place
        self.attack_cd = max(0, self.attack_cd - dt)
        self.dash_cd = max(0, self.dash_cd - dt)
        self.invuln = max(0, self.invuln - dt)
        self.coyote = max(0, self.coyote - dt)
        self.jump_buf = max(0, self.jump_buf - dt)

        # dying: gravity still pulls the body down, no input, wait for anim to end
        if self.dying:
            self.velocity[0] *= 0.85
            self.physics_update(self.e['Game'].physics_map)
            if self.animation and self.animation.finished:
                self.done = True
            self._tick_animation()
            return

        inp = self.e['Game'].input_source

        # start a dash: dodge with i-frames. Not allowed mid-swing — dodging is a
        # decision you commit to between attacks, not a cancel.
        if inp.pressed('dash') and not self.attacking and not self.dashing and self.dash_cd == 0:
            self.dash_time = DASH_SEC
            self.dash_cd = DASH_COOLDOWN
            held = inp.holding('right') - inp.holding('left')
            self.dash_dir = held if held != 0 else (-1 if self.flip[0] else 1)
            self.flip[0] = self.dash_dir < 0

        # attack/dash lock = no player movement input this frame
        locked = self.attacking or self.dashing
        dx = 0 if locked else inp.holding('right') - inp.holding('left')

        # buffer a jump press so a slightly-early tap still fires on landing
        if inp.pressed('jump') and not locked:
            self.jump_buf = JUMP_BUFFER

        # start a swing: must be unlocked and off cooldown
        if inp.pressed('attack') and not locked and self.attack_cd == 0:
            self.attacking = True
            self.attack_swing_id += 1
            self.attack_cd = ATTACK_COOLDOWN
            self.set_action('attack', force=True)

        # horizontal motion: dash overrides everything; drive velocity directly when
        # free; let knockback decay when attack-locked
        if self.dashing:
            self.dash_time -= dt
            self.velocity[0] = DASH_SPEED * self.dash_dir
            # flat dodge — suspend gravity so an air dash doesn't droop
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

        # consume a buffered jump if we have one available (real or coyote)
        if self.jump_buf > 0 and not self.dashing and (self.jumps_left > 0 or self.coyote > 0):
            self.velocity[1] = -JUMP_VEL
            self.air_time = 0.1
            self.jump_buf = 0
            self.coyote = 0
            self.jumps_left = max(0, self.jumps_left - 1)

        # variable-height jump: release jump early to cut the upward arc
        if not inp.holding('jump') and self.velocity[1] < -90:
            self.velocity[1] = -90

        # integrate velocity and resolve tile collisions
        self.physics_update(self.e['Game'].physics_map)

        # ground/air bookkeeping after the physics step
        on_ground = self.collide_directions['down']
        # `on_ground` blinks off for 3-4 frames at a time even while resting on flat
        # floor: pygame.Rect truncates the float pos to int and edge-touching rects
        # don't collide, so re-contact only registers once gravity sinks a whole
        # pixel. Drive the *animation* off the de-noised air_time instead — the blip
        # never exceeds COYOTE_TIME, but a real jump/fall does.
        airborne = self.air_time > COYOTE_TIME
        if on_ground:
            self.air_time = 0
            self.jumps_left = MAX_JUMPS
            self.coyote = COYOTE_TIME
        elif not self.dashing:
            # a dash zeroes vertical motion, so ground contact can't re-register
            # (down-collision needs downward movement) — freeze air_time instead of
            # letting a grounded dash (0.12s) cross the airborne threshold (0.08s)
            self.air_time += dt

        # animation state machine — priority: attack > dash > jump > run > idle
        if self.attacking:
            # clear the lock as soon as the swing animation finishes
            if self.animation and self.animation.finished:
                self.attacking = False
                self.animation.finished = False
            else:
                self.set_action('attack')
        elif self.dashing:
            # no dedicated dash sheet — the run cycle at dash speed reads as a sprint-burst
            self.set_action('run')
        elif airborne:
            # restart the jump animation on the real take-off frame; hold last frame after
            if not self.was_airborne:
                self.set_action('jump', force=True)
            else:
                self.set_action('jump')
        elif abs(dx) > 0:
            self.set_action('run')
        else:
            self.set_action('idle')

        self.was_airborne = airborne

        # i-frame blink: toggle visibility only. set_alpha() on RGBA sprites
        # (convert_alpha PNGs) often draws as a solid black box in pygame.
        if self.invuln > 0:
            self.visible = int(self.invuln * 20) % 2 == 1
        else:
            self.visible = True

        # advance the current animation by AT MOST one frame, gated on real wall-clock time
        self._tick_animation()
