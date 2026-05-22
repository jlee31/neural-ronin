# Hit feedback when the player takes damage.

import math
import random as rd
import pygame
from scripts.pygpen.vfx.sparks import Spark

ENABLE_HIT_PARTICLES = True #set to false if you want to disable
HIT_SPARK_COUNT = 10
HIT_DOT_COUNT = 6


class HitVFX:
    def __init__(self, rng=None):
        self.sparks = []
        self.dots = []
        self.rng = rng if rng is not None else rd

    def clear(self):
        self.sparks = []
        self.dots = []

    def spawn_player_hit(self, pos, source_x=None):
        """Emit the burst of sparks + dots that flashes when the player is hit.

        pos:      player center in world space — where the burst originates.
        source_x: world-x of the attacker. Used to aim the burst AWAY from them
                  so it reads as knockback. If None, the burst fans out in a
                  random direction (e.g. fall damage, environmental hits).
        """
        if not ENABLE_HIT_PARTICLES:
            return

        cx, cy = pos[0], pos[1]
        # base_angle = the "outward" direction the burst should spray.
        #   angle 0   → right (+x),   angle pi → left (-x).
        # If the attacker is to our left (source_x < cx) we spray right, and
        # vice versa — i.e. particles fly away from whoever hit us.
        if source_x is not None:
            base_angle = 0.0 if source_x < cx else math.pi
        else:
            base_angle = self.rng.uniform(0, math.tau)

        # ---- streak sparks (Spark = a stretched-diamond polygon drawn along
        #      its angle of motion; long-lived, fast, used for the "shing" lines).
        for _ in range(HIT_SPARK_COUNT):
            # ±0.9 rad ≈ ±50° spread → a tight cone around the knockback direction.
            angle = base_angle + self.rng.uniform(-0.9, 0.9)
            color = self.rng.choice(
                [(255, 70, 70), (255, 160, 90), (255, 240, 200), (255, 255, 255)]
            )
            self.sparks.append(
                Spark(
                    # jittered origin so all 10 sparks don't emit from one pixel
                    [cx + self.rng.uniform(-5, 5), cy + self.rng.uniform(-8, 4)],
                    angle,
                    # Spark.size is a 4-tuple (forward, side, back, side) describing
                    # the diamond's extents — randomizing each gives varied shapes.
                    size=(
                        self.rng.randint(5, 9),
                        self.rng.randint(1, 3),
                        self.rng.randint(4, 7),
                        self.rng.randint(1, 2),
                    ),
                    speed=self.rng.uniform(140, 260),
                    decay=self.rng.uniform(2.8, 4.5),  # higher decay = shorter-lived
                    color=color,
                    z=5,
                )
            )

        # ---- round dot particles: short-lived blood-spray; gravity is applied
        #      in update(), so these arc down after their initial pop.
        for _ in range(HIT_DOT_COUNT):
            # Wider cone (±1.2 rad ≈ ±70°) than sparks so dots scatter more chaotically.
            angle = base_angle + self.rng.uniform(-1.2, 1.2)
            speed = self.rng.uniform(90, 180)
            self.dots.append(
                {
                    "pos": [cx + self.rng.uniform(-3, 3), cy + self.rng.uniform(-6, 6)],
                    # Initial vy gets a -40 nudge upward so the burst "pops" up
                    # before gravity (320 px/s² in update) pulls it back down.
                    "vel": [math.cos(angle) * speed, math.sin(angle) * speed - 40],
                    "life": self.rng.uniform(0.18, 0.35),
                    "radius": self.rng.randint(2, 4),
                    "color": self.rng.choice([(255, 90, 90), (255, 200, 100)]),
                }
            )

    def update(self, dt):
        if not ENABLE_HIT_PARTICLES:
            self.clear()
            return

        # Spark.update() returns True when the spark dies, None otherwise — keep the
        # ones that did NOT return True.
        self.sparks = [s for s in self.sparks if not s.update(dt)]

        alive_dots = []
        for dot in self.dots:
            dot["life"] -= dt
            if dot["life"] <= 0:
                continue
            dot["pos"][0] += dot["vel"][0] * dt
            dot["pos"][1] += dot["vel"][1] * dt
            dot["vel"][1] += 320 * dt
            alive_dots.append(dot)
        self.dots = alive_dots

    def render(self, surf, offset=(0, 0)):
        if not ENABLE_HIT_PARTICLES:
            return

        for spark in self.sparks:
            spark.render(surf, offset=offset)

        for dot in self.dots:
            r = dot["radius"]
            color = dot["color"]
            px = int(dot["pos"][0] - offset[0])
            py = int(dot["pos"][1] - offset[1])
            pygame.draw.circle(surf, color, (px, py), r)
            pygame.draw.circle(surf, (255, 255, 255), (px, py), max(1, r - 1))
