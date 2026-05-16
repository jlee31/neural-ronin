import pygame

import scripts.pygpen as pp

# Tunables — adjust these to retune game feel.
GRAVITY = 500            # px/s^2 constant downward pull
JUMP_VEL = 280           # initial upward velocity on jump
RUN_SPEED = 130          # horizontal speed in px/s
MAX_FALL = 330           # terminal fall speed cap
MAX_JUMPS = 2            # 1 ground jump + 1 air jump
COYOTE_TIME = 0.08       # ledge-fall forgiveness window
JUMP_BUFFER = 0.10       # early-press forgiveness window
ATTACK_COOLDOWN = 0.45   # seconds between swings
INVULN_TIME = 0.60       # i-frames after a hit
KNOCKBACK_X = 160        # horizontal punch on hit
KNOCKBACK_Y = -120       # small upward pop on hit
MAX_HEALTH = 5


class Player(pp.PhysicsEntity):
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
        self.dying = False        # death animation is playing
        self.done = False         # death animation finished — safe to respawn

        # tick-based animation timing (MagesticBrawl-style)
        # avoids pygpen's dt-accumulation sprinting through frames when fps stutters
        self.anim_last_tick_ms = pygame.time.get_ticks()

    @property
    def alive(self):
        # "alive" means the run is still ongoing — death anim must finish first
        return not self.done

    def set_action(self, action, force=False):
        # reset the per-frame timer whenever the action actually changes so the new anim starts fresh
        changed = force or self.action != action
        super().set_action(action, force=force)
        if changed:
            self.anim_last_tick_ms = pygame.time.get_ticks()

    def _tick_animation(self):
        # advance at most ONE frame per call, based on the current frame's configured duration.
        # this is the MagesticBrawl pattern: never sprint through frames on a slow tick.
        a = self.animation
        if a is None:
            return
        frame_idx = min(len(a.images) - 1, a.frame)
        cooldown_ms = int(a.config['frames'][frame_idx] * 1000)
        now = pygame.time.get_ticks()
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
        # ignored during i-frames or once we're already dying
        if self.invuln > 0 or self.health <= 0:
            return
        self.health = max(0, self.health - amount)
        self.invuln = INVULN_TIME
        self.attacking = False    # cancel any in-progress swing

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

    def update(self):
        dt = self.e['Window'].dt
        # NOTE: deliberately NOT calling super().update(dt) — that would run pygpen's
        # dt-accumulation animation tick. We drive the animation manually below via
        # _tick_animation() so it can never advance more than one frame per game tick.

        # tick all transient timers in one place
        self.attack_cd = max(0, self.attack_cd - dt)
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

        inp = self.e['Input']
        # attack lock = no player movement input this frame
        locked = self.attacking
        dx = 0 if locked else inp.holding('right') - inp.holding('left')

        # buffer a jump press so a slightly-early tap still fires on landing
        if inp.pressed('jump') and not locked:
            self.jump_buf = JUMP_BUFFER

        # start a swing: must be unlocked and off cooldown
        if inp.pressed('attack') and not locked and self.attack_cd == 0:
            self.attacking = True
            self.attack_cd = ATTACK_COOLDOWN
            self.set_action('attack', force=True)

        # horizontal motion: drive velocity directly when free; let knockback decay when locked
        if not locked:
            self.velocity[0] = dx * RUN_SPEED
            if dx > 0:
                self.flip[0] = False
            elif dx < 0:
                self.flip[0] = True
        else:
            self.velocity[0] *= 0.90

        # consume a buffered jump if we have one available (real or coyote)
        if self.jump_buf > 0 and (self.jumps_left > 0 or self.coyote > 0):
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
        else:
            self.air_time += dt

        # animation state machine — priority: attack > jump > run > idle
        if self.attacking:
            # clear the lock as soon as the swing animation finishes
            if self.animation and self.animation.finished:
                self.attacking = False
                self.animation.finished = False
            else:
                self.set_action('attack')
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

        # flicker the sprite while invulnerable for visual feedback
        if self.invuln > 0 and int(self.invuln * 20) % 2 == 0:
            self.opacity = 120
        else:
            self.opacity = 255

        # advance the current animation by AT MOST one frame, gated on real wall-clock time
        self._tick_animation()
