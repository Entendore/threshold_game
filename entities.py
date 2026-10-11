import math
import numpy as np
import pygame
from core import WIDTH, HEIGHT, MAX_TRAIL, lerp
from level import LevelLoader, LevelData

class Player:
    def __init__(self, pos, angle=-math.pi / 2, color=(1.0, 0.92, 0.43)):
        self.pos = pos
        self.angle = angle
        self.vel = np.zeros(2, dtype=np.float32)
        self.radius = 12.0
        self.trail = []
        self.trail_timer = 0.0
        self.dash_cd = 0.0
        self.dash_time = 0.0
        self.dash_buffer = 0.0
        self.invuln = 0.0
        self.hp = 3
        self.max_hp = 3
        self.scale = np.array([1.0, 1.0], dtype=np.float32)
        self.thrusting = False
        self.color = color

    def update(self, dt, level: LevelData, t, rotate_input, thrust_input, brake_input):
        events = []
        if dt <= 0: return events

        # Input Buffering for Dash
        if self.dash_buffer > 0:
            self.dash_buffer -= dt
            if self.dash_cd <= 0:
                forward = np.array([math.cos(self.angle), math.sin(self.angle)], dtype=np.float32)
                self.dash_time = 0.18
                self.dash_cd = 1.2
                self.invuln = max(self.invuln, 0.25)
                self.vel = forward * 700.0
                self.scale = np.array([1.3, 0.8], dtype=np.float32)
                events.append({"type": "dash", "pos": self.pos.copy()})
                self.dash_buffer = 0.0

        rot_speed = 3.5
        self.angle += rotate_input * rot_speed * dt
        self.thrusting = thrust_input > 0

        self.dash_cd = max(0, self.dash_cd - dt)
        self.dash_time = max(0, self.dash_time - dt)
        self.invuln = max(0, self.invuln - dt)
        self.scale += (np.array([1.0, 1.0], dtype=np.float32) - self.scale) * min(1.0, dt * 10.0)

        forward = np.array([math.cos(self.angle), math.sin(self.angle)], dtype=np.float32)
        accel = 3500.0 if self.dash_time > 0 else 2200.0
        max_speed = 650.0 if self.dash_time > 0 else 380.0

        if thrust_input:
            self.vel = self.vel + forward * accel * dt

        if brake_input:
            self.vel = self.vel * max(0.0, 1.0 - 8.0 * dt)
        else:
            friction = 4.0 if self.dash_time > 0 else 2.8
            self.vel = self.vel * max(0.0, 1.0 - friction * dt)

        speed = float(np.linalg.norm(self.vel))
        if speed > max_speed:
            self.vel = self.vel * (max_speed / speed)
            speed = max_speed

        remaining_dist = speed * dt
        dir_vec = self.vel / max(speed, 1e-6)
        safety = 0
        while remaining_dist > 0.1 and safety < 10:
            safety += 1
            d, is_hazard, hit_obj = LevelLoader.evaluate_sdf(level, self.pos, t)
            if d < self.radius:
                n = LevelLoader.normal_at(level, self.pos, t)
                if is_hazard and self.invuln <= 0:
                    events.append({"type": "hit", "pos": self.pos.copy(), "normal": n.copy()})
                    self._take_damage(n)
                    return events
                else:
                    push = (self.radius - d) + 0.5
                    self.pos = self.pos + n * push
                    vn = float(np.dot(self.vel, n))
                    if vn < 0:
                        impact = -vn
                        bounce_amt = getattr(hit_obj, 'bounce', 0.0) if hit_obj else 0.0
                        if bounce_amt > 0:
                            self.vel = self.vel - (1.0 + bounce_amt) * vn * n
                            events.append({"type": "bounce", "pos": self.pos.copy(), "normal": n.copy(), "impact": impact})
                            self.scale = np.array([1.0 + abs(n[0])*0.4, 1.0 - abs(n[0])*0.2], dtype=np.float32)
                        else:
                            self.vel = self.vel - (1.0 + 0.15) * vn * n
                            if impact > 30:
                                events.append({"type": "wall_hit", "pos": self.pos.copy(), "normal": n.copy(), "impact": impact})
                dir_vec = self.vel / max(float(np.linalg.norm(self.vel)), 1e-6)
                remaining_dist = float(np.linalg.norm(self.vel * dt))
            else:
                safe_dist = max(0.1, d - self.radius)
                move = min(remaining_dist, safe_dist)
                self.pos = self.pos + dir_vec * move
                remaining_dist -= move

        self.trail_timer += dt
        if self.trail_timer > 0.025:
            self.trail.append(self.pos.copy()); self.trail_timer = 0.0
        self.trail = self.trail[-MAX_TRAIL:]
        return events

    def buffer_dash(self):
        self.dash_buffer = 0.15

    def _take_damage(self, n):
        self.hp -= 1
        self.invuln = 1.0
        self.vel = -n * 450.0
        self.dash_time = 0

    def get_trail_shader_data(self):
        count = len(self.trail)
        data = np.zeros((MAX_TRAIL, 3), dtype=np.float32)
        for i, pos in enumerate(self.trail):
            age = i / max(count - 1, 1)
            data[i] = [pos[0], pos[1], age]
        return data, count

class Camera:
    def __init__(self):
        self.zoom = 1.0
        self.target_zoom = 1.0
        self.shake_amp = 0.0
        self.offset = np.zeros(2, dtype=np.float32)
    def update(self, dt, reduce_motion=False):
        self.zoom = lerp(self.zoom, self.target_zoom, min(1.0, dt * 5.0))
        if reduce_motion:
            self.shake_amp = 0.0; self.offset[:] = 0; return
        self.shake_amp *= math.exp(-5.0 * dt)
        if self.shake_amp < 0.1: self.shake_amp = 0.0; self.offset[:] = 0
        else:
            t = pygame.time.get_ticks() / 1000.0
            self.offset[0] = (math.sin(t * 31.7) * 0.7 + math.sin(t * 47.3) * 0.3) * self.shake_amp
            self.offset[1] = (math.sin(t * 29.3) * 0.6 + math.sin(t * 53.1) * 0.4) * self.shake_amp
    def add_shake(self, amount, reduce_motion=False):
        if reduce_motion: return
        self.shake_amp = min(12.0, self.shake_amp + amount)
