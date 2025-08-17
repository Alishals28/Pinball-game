import math
import random
import sys
from dataclasses import dataclass, field
from collections import deque
from pathlib import Path

import pygame

# ----------------------------------
# Config
# ----------------------------------
WIDTH, HEIGHT = 500, 650
FPS = 120
GRAVITY = 2000.0        # px/s^2 downward
AIR_FRICTION = 0.0005   # proportional damping
RESTI_BALL_WALL = 0.85
RESTI_BALL_BUMPER = 1.05
RESTI_BALL_FLIPPER = 1.0
TANGENTIAL_FRICTION = 0.02
MAX_BALL_SPEED = 2400.0

BALL_RADIUS = 12
BALL_MASS = 1.0

FLIPPER_LENGTH = 140
FLIPPER_WIDTH = 16
FLIPPER_SPEED = math.radians(900)  # deg/s in radians
FLIPPER_LEFT_MIN = math.radians(15)
FLIPPER_LEFT_MAX = math.radians(70)
FLIPPER_RIGHT_MIN = -math.radians(70)
FLIPPER_RIGHT_MAX = -math.radians(15)

PLUNGER_MAX = 480.0  # launch power
PLUNGER_CHARGE_RATE = 900.0

START_BALLS = 3
BALL_SAVE_TIME = 8.0    # seconds of ball save after launch
NUDGE_IMPULSE = 260.0   # px/s instant velocity tweak
TILT_MAX = 3            # nudges before tilt
TILT_DECAY = 0.4        # per second decay of tilt meter
TILT_LOCKOUT = 4.0      # seconds tilt disables controls

TRAIL_POINTS = 14
PARTICLE_COUNT_HIT = (10, 18)
PARTICLE_GRAV = 900.0
PARTICLE_FADE = 0.85

pygame.init()
Vec2 = pygame.math.Vector2
FONT = pygame.font.SysFont("consolas", 26)
BIG = pygame.font.SysFont("consolas", 48)
SMALL = pygame.font.SysFont("consolas", 20)


def clamp(x, lo, hi):
    return max(lo, min(hi, x))


def reflect(v: Vec2, n: Vec2, restitution: float) -> Vec2:
    vn = v.dot(n)
    if vn < 0:
        v = v - (1.0 + restitution) * vn * n
    return v


def circle_line_collision(c: Vec2, r: float, a: Vec2, b: Vec2):
    # Returns (hit, push_vec, normal, closest_point, t)
    ab = b - a
    ab2 = ab.length_squared()
    if ab2 == 0:
        # treat degenerate as circle-circle with point
        diff = c - a
        dist = diff.length() + 1e-9
        if dist < r:
            n = diff / dist
            return True, n * (r - dist), n, a, 0.0
        return False, Vec2(), Vec2(), Vec2(), 0.0
    t = clamp((c - a).dot(ab) / ab2, 0.0, 1.0)
    closest = a + t * ab
    diff = c - closest
    dist = diff.length() + 1e-9
    if dist < r:
        n = diff / dist
        push = n * (r - dist)
        return True, push, n, closest, t
    return False, Vec2(), Vec2(), closest, t


def circle_circle_collision(c1: Vec2, r1: float, c2: Vec2, r2: float):
    diff = c1 - c2
    d = diff.length() + 1e-9
    if d < r1 + r2:
        n = diff / d
        push = n * (r1 + r2 - d)
        return True, push, n
    return False, Vec2(), Vec2()


@dataclass
class Wall:
    a: Vec2
    b: Vec2
    color: tuple = (220, 220, 220)
    score: int = 5
    restitution: float = RESTI_BALL_WALL


@dataclass
class Bumper:
    pos: Vec2
    radius: float
    score: int = 100
    color: tuple = (255, 215, 0)

    def draw(self, surf):
        pygame.draw.circle(surf, self.color, self.pos, self.radius)
        pygame.draw.circle(surf, (255, 255, 255), self.pos, self.radius, 3)


@dataclass
class Rollover:
    pos: Vec2
    radius: float = 14
    lit: bool = False
    score: int = 250

    def draw(self, surf):
        col = (120, 220, 255) if self.lit else (70, 100, 130)
        pygame.draw.circle(surf, col, self.pos, self.radius)
        pygame.draw.circle(surf, (200, 230, 255), self.pos, self.radius, 2)

    def check(self, ball_pos: Vec2, ball_r: float) -> bool:
        # Trigger when the ball overlaps; returns True if newly lit
        if self.lit:
            return False
        if (ball_pos - self.pos).length() < self.radius + ball_r * 0.6:
            self.lit = True
            return True
        return False


@dataclass
class Particle:
    pos: Vec2
    vel: Vec2
    color: tuple
    life: float  # seconds remaining

    def update(self, dt: float):
        # simple gravity and damping
        self.vel.y += PARTICLE_GRAV * dt
        self.pos += self.vel * dt
        self.life -= dt

    def draw(self, surf):
        if self.life <= 0:
            return
        alpha = clamp(int(255 * (self.life)), 0, 255)
        col = (self.color[0], self.color[1], self.color[2])
        # draw as tiny circle; pygame doesn't support per-primitive alpha easily without surfaces
        pygame.draw.circle(surf, col, (int(self.pos.x), int(self.pos.y)), 2)


class Flipper:
    def __init__(self, pivot: Vec2, length: float, is_left: bool):
        self.pivot = pivot
        self.length = length
        self.is_left = is_left
        if is_left:
            self.angle = FLIPPER_LEFT_MIN
            self.min_angle = FLIPPER_LEFT_MIN
            self.max_angle = FLIPPER_LEFT_MAX
            self.key_pressed = False
        else:
            self.angle = FLIPPER_RIGHT_MIN
            self.min_angle = FLIPPER_RIGHT_MIN
            self.max_angle = FLIPPER_RIGHT_MAX
            self.key_pressed = False
        self.ang_vel = 0.0  # rad/s

    def endpoints(self):
        # Flipper runs from pivot to tip at current angle
        dir_vec = Vec2(math.cos(self.angle), -math.sin(self.angle))
        tip = self.pivot + dir_vec * self.length
        return self.pivot, tip

    def update(self, dt):
        target = self.max_angle if self.key_pressed else self.min_angle
        # Move towards target by FLIPPER_SPEED, track angular velocity
        prev_angle = self.angle
        if self.angle < target:
            self.angle = min(self.angle + FLIPPER_SPEED * dt, target)
        elif self.angle > target:
            self.angle = max(self.angle - FLIPPER_SPEED * dt, target)
        self.ang_vel = (self.angle - prev_angle) / max(dt, 1e-6)

    def draw(self, surf):
        a, b = self.endpoints()
        # Draw a thick capsule-like flipper
        n = (b - a)
        ln = n.length() + 1e-9
        if ln > 0:
            n = n / ln
            t = Vec2(-n.y, n.x)
        else:
            t = Vec2(0, -1)
        w = FLIPPER_WIDTH / 2
        p1 = a + t * w
        p2 = b + t * w
        p3 = b - t * w
        p4 = a - t * w
        pygame.draw.polygon(surf, (230, 70, 70), [p1, p2, p3, p4])
        pygame.draw.circle(surf, (255, 255, 255), a, int(w), 2)
        pygame.draw.circle(surf, (255, 255, 255), b, int(w), 2)


class Ball:
    def __init__(self, pos: Vec2):
        self.pos = Vec2(pos)
        self.vel = Vec2(0, 0)
        self.radius = BALL_RADIUS
        self.mass = BALL_MASS
        self.in_play = False  # requires launch
        self.trail: deque[Vec2] = deque(maxlen=TRAIL_POINTS)

    def apply_physics(self, dt):
        if not self.in_play:
            return
        # gravity
        self.vel.y += GRAVITY * dt
        # air drag (simple)
        self.vel *= (1.0 - AIR_FRICTION) ** (dt * 60.0)
        # clamp speed
        sp = self.vel.length()
        if sp > MAX_BALL_SPEED:
            self.vel = self.vel * (MAX_BALL_SPEED / sp)
        self.pos += self.vel * dt
        # trail record
        self.trail.append(Vec2(self.pos))

    def draw(self, surf):
        # draw trail first (faded)
        if len(self.trail) > 2:
            for i, p in enumerate(self.trail):
                t = (i + 1) / len(self.trail)
                r = max(1, int(self.radius * 0.4 * t))
                col = (80, 120, 200)
                pygame.draw.circle(surf, col, (int(p.x), int(p.y)), r)
        pygame.draw.circle(surf, (240, 240, 255), self.pos, self.radius)
        pygame.draw.circle(surf, (80, 120, 200), self.pos, self.radius, 2)


class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption("Old-School Pinball")
        self.clock = pygame.time.Clock()
        self.running = True

        # Table boundaries (leave a right lane visual; gameplay inside main field)
        margin = 80
        bottom_y = HEIGHT - 80
        # Side and top walls for main field
        self.walls = [
            Wall(Vec2(margin, 140), Vec2(margin, bottom_y)),               # left wall
            Wall(Vec2(margin, 140), Vec2(WIDTH - margin - 100, 140)),      # top wall
            Wall(Vec2(WIDTH - margin - 100, 140), Vec2(WIDTH - margin - 100, bottom_y - 180)),  # right wall
            # Bottom inlanes to drain
            Wall(Vec2(margin, bottom_y), Vec2(WIDTH / 2 - 80, HEIGHT - 20)),
            Wall(Vec2(WIDTH - margin - 100, bottom_y - 180), Vec2(WIDTH - margin - 60, bottom_y - 60)),
            Wall(Vec2(WIDTH - margin - 60, bottom_y - 60), Vec2(WIDTH / 2 + 80, HEIGHT - 20)),
            # Slingshots (extra bouncy)
            Wall(Vec2(WIDTH * 0.28, bottom_y - 40), Vec2(WIDTH * 0.42, bottom_y - 110), color=(255,150,150), score=25, restitution=1.2),
            Wall(Vec2(WIDTH * 0.72, bottom_y - 40), Vec2(WIDTH * 0.58, bottom_y - 110), color=(255,150,150), score=25, restitution=1.2),
        ]

    # Bumpers (triad + scatter)
        self.bumpers = [
            Bumper(Vec2(WIDTH * 0.35, 300), 38, 150),
            Bumper(Vec2(WIDTH * 0.55, 300), 38, 150),
            Bumper(Vec2(WIDTH * 0.45, 220), 38, 200),
            Bumper(Vec2(WIDTH * 0.32, 480), 28, 100),
            Bumper(Vec2(WIDTH * 0.58, 520), 28, 100),
            Bumper(Vec2(WIDTH * 0.46, 620), 24, 75),
        ]

    # Rollovers at the top lanes (bonus when all lit)
        self.rollovers = [
            Rollover(Vec2(WIDTH * 0.35, 160)),
            Rollover(Vec2(WIDTH * 0.45, 160)),
            Rollover(Vec2(WIDTH * 0.55, 160)),
        ]

        # Flippers
        pivot_y = HEIGHT - 120
        self.left_flipper = Flipper(Vec2(WIDTH * 0.35, pivot_y), FLIPPER_LENGTH, True)
        self.right_flipper = Flipper(Vec2(WIDTH * 0.65, pivot_y), FLIPPER_LENGTH, False)

        # Ball and launch
        self.ball = Ball(Vec2(WIDTH - 140, HEIGHT - 140))
        self.plunger_power = 0.0
        self.ball_save_timer = 0.0
        self.ball_save_active = False

        # Game state
        self.score = 0
        self.high_score = self.load_high_score()
        self.balls_left = START_BALLS
        self.paused = False
        self.game_over = False
        self.just_lost = False
        self.bonus_mult = 1
        self.bumper_mult = 1
        self.bumper_mult_timer = 0.0

        # Nudge/Tilt
        self.tilt_meter = 0.0
        self.tilt_active = False
        self.tilt_timer = 0.0

        # Simple table background pre-draw
        self.bg = pygame.Surface((WIDTH, HEIGHT))
        self.draw_table_bg(self.bg)

        # Particles
        self.particles: list[Particle] = []

    def load_high_score(self) -> int:
        try:
            path = Path(__file__).with_name("highscore.txt")
            if path.exists():
                return int(path.read_text().strip() or 0)
        except Exception:
            pass
        return 0

    def save_high_score(self):
        try:
            path = Path(__file__).with_name("highscore.txt")
            path.write_text(str(self.high_score))
        except Exception:
            pass

    def draw_table_bg(self, surf):
        surf.fill((12, 18, 28))
        # Playfield area
        pygame.draw.rect(surf, (10, 40, 60), (60, 120, WIDTH - 220, HEIGHT - 200), border_radius=24)
        # Plunger lane visual
        pygame.draw.rect(surf, (18, 26, 36), (WIDTH - 140, 120, 80, HEIGHT - 200), border_radius=24)
        # Walls
        for w in self.walls:
            pygame.draw.line(surf, w.color, w.a, w.b, 6)

        # Labels
        label = BIG.render("PINBALL", True, (240, 240, 255))
        surf.blit(label, (60, 60))
        tip = SMALL.render("SPACE: Launch • Z/← and / or →: Flip • N: Nudge • P: Pause", True, (180, 200, 220))
        surf.blit(tip, (60, 100))

    def reset_ball(self):
        # Place ball near right-bottom "plunger zone"
        self.ball = Ball(Vec2(WIDTH - 140, HEIGHT - 140))
        self.plunger_power = 0.0
        self.just_lost = False
        self.ball_save_active = False
        self.ball_save_timer = 0.0

    def launch_ball(self):
        # Launch into playfield with some right-to-left and upward velocity
        if self.ball.in_play:
            return
        angle = random.uniform(math.radians(100), math.radians(120))  # mostly up-left
        speed = self.plunger_power + 400.0
        vx = math.cos(angle) * speed
        vy = -math.sin(angle) * speed
        self.ball.vel = Vec2(vx, vy)
        self.ball.in_play = True
        self.plunger_power = 0.0
        # enable ball save window
        self.ball_save_active = True
        self.ball_save_timer = BALL_SAVE_TIME

    def handle_events(self, dt):
        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                self.running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    self.running = False
                if not self.tilt_active and e.key in (pygame.K_LEFT, pygame.K_z):
                    self.left_flipper.key_pressed = True
                if not self.tilt_active and e.key in (pygame.K_RIGHT, pygame.K_SLASH, pygame.K_QUESTION):
                    self.right_flipper.key_pressed = True
                if e.key == pygame.K_p:
                    if not self.game_over:
                        self.paused = not self.paused
                if e.key == pygame.K_r:
                    if self.game_over:
                        self.restart()
                if e.key == pygame.K_n and self.ball.in_play and not self.paused and not self.game_over:
                    self.do_nudge()
            elif e.type == pygame.KEYUP:
                if e.key in (pygame.K_LEFT, pygame.K_z):
                    self.left_flipper.key_pressed = False
                if e.key in (pygame.K_RIGHT, pygame.K_SLASH, pygame.K_QUESTION):
                    self.right_flipper.key_pressed = False

        # Plunger charge
        keys = pygame.key.get_pressed()
        if not self.ball.in_play and not self.game_over and not self.paused:
            if keys[pygame.K_SPACE]:
                self.plunger_power = clamp(self.plunger_power + PLUNGER_CHARGE_RATE * dt, 0, PLUNGER_MAX)
            else:
                if self.plunger_power > 0:
                    self.launch_ball()

    def update(self, dt):
        if self.paused or self.game_over:
            return

        # Update flippers
        self.left_flipper.update(dt)
        self.right_flipper.update(dt)

        # Ball physics
        self.ball.apply_physics(dt)

        # Collisions: walls
        self.handle_wall_collisions()

        # Bumpers
        self.handle_bumper_collisions()

        # Rollovers and bonus state
        self.handle_rollovers()

        # Flippers
        self.handle_flipper_collision(self.left_flipper)
        self.handle_flipper_collision(self.right_flipper)

        # Particles update
        self.particles_update(dt)

        # Bonus timers
        if self.bumper_mult_timer > 0:
            self.bumper_mult_timer -= dt
            if self.bumper_mult_timer <= 0:
                self.bumper_mult = 1

        # Tilt timer and decay
        if self.tilt_active:
            self.tilt_timer -= dt
            if self.tilt_timer <= 0:
                self.tilt_active = False
        else:
            # meter decays slowly when not tilted
            self.tilt_meter = max(0.0, self.tilt_meter - TILT_DECAY * dt)

        # Ball save timer
        if self.ball_save_active:
            self.ball_save_timer -= dt
            if self.ball_save_timer <= 0:
                self.ball_save_active = False

        # Drain check
        if self.ball.in_play and self.ball.pos.y - self.ball.radius > HEIGHT + 40:
            if self.ball_save_active:
                # Save the ball: relaunch from plunger
                self.ball.in_play = False
                self.reset_ball()
            else:
                self.balls_left -= 1
                self.ball.in_play = False
                self.just_lost = True
                if self.balls_left <= 0:
                    self.game_over = True
                    self.high_score = max(self.high_score, self.score)
                    self.save_high_score()
                else:
                    # Prepare next ball
                    self.reset_ball()

    def handle_wall_collisions(self):
        for w in self.walls:
            hit, push, n, _, _ = circle_line_collision(self.ball.pos, self.ball.radius, w.a, w.b)
            if hit:
                self.ball.pos += push
                # tangential slow
                t = Vec2(-n.y, n.x)
                vt = self.ball.vel.dot(t)
                vn = self.ball.vel.dot(n)
                vt *= (1.0 - TANGENTIAL_FRICTION)
                self.ball.vel = vt * t + vn * n
                self.ball.vel = reflect(self.ball.vel, n, getattr(w, 'restitution', RESTI_BALL_WALL))
                if self.ball.in_play:
                    self.score += w.score
                    self.spawn_particles(self.ball.pos, n, (200, 220, 255))

        # Keep ball inside left/top/right borders softly (safety)
        margin = 74
        if self.ball.pos.x - self.ball.radius < margin:
            self.ball.pos.x = margin + self.ball.radius
            self.ball.vel.x = abs(self.ball.vel.x) * RESTI_BALL_WALL
        if self.ball.pos.x + self.ball.radius > WIDTH - 160:
            self.ball.pos.x = WIDTH - 160 - self.ball.radius
            self.ball.vel.x = -abs(self.ball.vel.x) * RESTI_BALL_WALL
        if self.ball.pos.y - self.ball.radius < 120 + 16:
            self.ball.pos.y = 120 + 16 + self.ball.radius
            self.ball.vel.y = abs(self.ball.vel.y) * RESTI_BALL_WALL

    def handle_bumper_collisions(self):
        for b in self.bumpers:
            hit, push, n = circle_circle_collision(self.ball.pos, self.ball.radius, b.pos, b.radius)
            if hit:
                self.ball.pos += push
                self.ball.vel = reflect(self.ball.vel, n, RESTI_BALL_BUMPER)
                # Add a small outward impulse
                self.ball.vel += n * 200.0
                if self.ball.in_play:
                    self.score += b.score * self.bumper_mult
                    self.spawn_particles(self.ball.pos, n, (255, 230, 120))

    def handle_rollovers(self):
        newly = 0
        for r in self.rollovers:
            if r.check(self.ball.pos, self.ball.radius):
                newly += 1
                if self.ball.in_play:
                    self.score += r.score
                    self.spawn_particles(r.pos, Vec2(0, -1), (120, 220, 255))
        if self.ball.in_play and all(r.lit for r in self.rollovers):
            # award and start bumper multiplier bonus
            self.score += 1000
            self.bumper_mult = 2
            self.bumper_mult_timer = 15.0
            # reset lights for next round
            for r in self.rollovers:
                r.lit = False

    def handle_flipper_collision(self, flipper: Flipper):
        a, b = flipper.endpoints()
        hit, push, n, contact, t = circle_line_collision(self.ball.pos, self.ball.radius, a, b)
        if not hit:
            return
        # Push out
        self.ball.pos += push

        # Basic reflection
        self.ball.vel = reflect(self.ball.vel, n, RESTI_BALL_FLIPPER)

        # Add impulse from flipper's angular motion at contact point
        # Compute contact relative to pivot; point velocity ~ omega x r (perp)
        r = contact - flipper.pivot
        # Perp rotate by 90 deg: (x, y) -> (-y, x)
        v_point = Vec2(-r.y, r.x) * flipper.ang_vel
        # Boost along normal if flipper moving into the ball
        boost = v_point.dot(n)
        if boost > 0:
            self.ball.vel += n * boost * 0.9

        # Small scoring for skill shots on flipper
        if self.ball.in_play:
            self.score += 1
            self.spawn_particles(contact, n, (230, 70, 70))

    def spawn_particles(self, pos: Vec2, normal: Vec2, color: tuple):
        cnt = random.randint(*PARTICLE_COUNT_HIT)
        for _ in range(cnt):
            ang = math.atan2(-normal.y, -normal.x) + random.uniform(-0.8, 0.8)

            spd = random.uniform(100.0, 420.0)
            v = Vec2(math.cos(ang) * spd, -math.sin(ang) * spd)
            self.particles.append(Particle(Vec2(pos), v, color, life=random.uniform(0.3, 0.8)))

    def particles_update(self, dt: float):
        alive = []
        for p in self.particles:
            p.update(dt)
            if p.life > 0:
                alive.append(p)
        self.particles = alive

    def do_nudge(self):
        # Apply small horizontal impulse and raise tilt meter
        dir_sign = random.choice([-1, 1])
        self.ball.vel.x += dir_sign * NUDGE_IMPULSE
        self.tilt_meter += 1.0
        if self.tilt_meter >= TILT_MAX and not self.tilt_active:
            self.tilt_active = True
            self.tilt_timer = TILT_LOCKOUT
            # lock flippers off during tilt
            self.left_flipper.key_pressed = False
            self.right_flipper.key_pressed = False

    def draw_hud(self, surf):
        hud = FONT.render(f"Score: {self.score}", True, (240, 240, 255))
        lives = FONT.render(f"Balls: {self.balls_left}", True, (240, 240, 255))
        hs = FONT.render(f"High: {self.high_score}", True, (200, 220, 255))
        surf.blit(hud, (60, HEIGHT - 60))
        surf.blit(lives, (280, HEIGHT - 60))
        surf.blit(hs, (480, HEIGHT - 60))

        if self.paused:
            p = BIG.render("PAUSED", True, (255, 230, 120))
            surf.blit(p, (WIDTH / 2 - p.get_width() / 2, HEIGHT / 2 - p.get_height() / 2))

        if not self.ball.in_play and not self.game_over:
            # Draw plunger meter
            x, y, w, h = WIDTH - 120, HEIGHT - 260, 24, 180
            pygame.draw.rect(surf, (70, 90, 120), (x, y, w, h), border_radius=6)
            ratio = self.plunger_power / PLUNGER_MAX
            fill_h = int(h * ratio)
            pygame.draw.rect(surf, (120, 200, 255), (x + 3, y + h - fill_h + 3, w - 6, fill_h - 6), border_radius=4)
            cap = SMALL.render("PLUNGER", True, (180, 200, 220))
            surf.blit(cap, (x - 20, y - 24))

        if self.game_over:
            g = BIG.render("GAME OVER", True, (255, 160, 160))
            s = FONT.render("Press R to Restart • ESC to Quit", True, (220, 220, 240))
            surf.blit(g, (WIDTH / 2 - g.get_width() / 2, HEIGHT / 2 - 80))
            surf.blit(s, (WIDTH / 2 - s.get_width() / 2, HEIGHT / 2))

        # Bonus and status indicators
        if self.bumper_mult > 1 and self.bumper_mult_timer > 0:
            m = FONT.render(f"Bumper x{self.bumper_mult}", True, (255, 230, 120))
            surf.blit(m, (60, HEIGHT - 90))
        if self.ball_save_active:
            bs = FONT.render("BALL SAVE", True, (120, 255, 180))
            surf.blit(bs, (WIDTH - 240, HEIGHT - 90))
        if self.tilt_active:
            t = BIG.render("TILT", True, (255, 120, 120))
            surf.blit(t, (WIDTH / 2 - t.get_width() / 2, HEIGHT / 2 + 80))
        else:
            if self.tilt_meter > 0.1:
                tm = SMALL.render(f"Nudge: {self.tilt_meter:.1f}/{TILT_MAX}", True, (200, 200, 200))
                surf.blit(tm, (WIDTH - 220, 60))

    def restart(self):
        self.score = 0
        self.balls_left = START_BALLS
        self.game_over = False
        self.paused = False
        self.reset_ball()
        self.bonus_mult = 1
        self.bumper_mult = 1
        self.bumper_mult_timer = 0.0
        for r in self.rollovers:
            r.lit = False
        self.tilt_meter = 0.0
        self.tilt_active = False
        self.particles.clear()

    def draw(self):
        self.screen.blit(self.bg, (0, 0))

        # Bumpers
        for b in self.bumpers:
            b.draw(self.screen)

        # Rollovers
        for r in self.rollovers:
            r.draw(self.screen)

        # Flippers
        self.left_flipper.draw(self.screen)
        self.right_flipper.draw(self.screen)

        # Ball
        self.ball.draw(self.screen)

        # Particles on top of everything for clarity
        for p in self.particles:
            p.draw(self.screen)

        # HUD
        self.draw_hud(self.screen)

        pygame.display.flip()

    def run(self):
        self.reset_ball()
        while self.running:
            dt = self.clock.tick(FPS) / 1000.0
            self.handle_events(dt)
            self.update(dt)
            self.draw()
        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    Game().run()
