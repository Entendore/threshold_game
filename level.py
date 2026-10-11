import math
import numpy as np
from dataclasses import dataclass, field
from typing import List, Dict, Any
from core import WIDTH, HEIGHT, sd_circle, sd_segment, sd_box

@dataclass
class Shape:
    center: np.ndarray
    color: tuple = (0.9, 0.43, 0.86)
    bounce: float = 0.0

@dataclass
class BoxShape(Shape):
    half_size: np.ndarray = field(default_factory=lambda: np.array([20.0, 20.0]))
    rot: float = 0.0
    rot_speed: float = 0.0

@dataclass
class CircleShape(Shape):
    radius: float = 30.0

@dataclass
class MovingShape:
    shape: Shape
    motion_type: str = "linear"
    pos1: np.ndarray = field(default_factory=lambda: np.zeros(2))
    pos2: np.ndarray = field(default_factory=lambda: np.zeros(2))
    center: np.ndarray = field(default_factory=lambda: np.zeros(2))
    radius: float = 50.0
    speed: float = 1.0
    phase: float = 0.0
    def update(self, t):
        if self.motion_type == "circular":
            ang = t * self.speed + self.phase
            self.shape.center = self.center + np.array([math.cos(ang), math.sin(ang)]) * self.radius
        elif self.motion_type == "lissajous":
            x = math.sin(t * self.speed + self.phase)
            y = math.sin(t * self.speed * 1.5 + self.phase * 1.3)
            self.shape.center = self.center + np.array([x * self.pos1[0], y * self.pos1[1]])
        else: # linear
            s = (math.sin(t * self.speed + self.phase) + 1.0) / 2.0
            self.shape.center = self.pos1 * (1.0 - s) + self.pos2 * s
        
        if isinstance(self.shape, BoxShape) and self.shape.rot_speed != 0:
            self.shape.rot = t * self.shape.rot_speed + self.phase

@dataclass
class LevelData:
    name: str = "Untitled Zone"
    spawn: np.ndarray = field(default_factory=lambda: np.array([WIDTH/2, HEIGHT-100], dtype=np.float32))
    spawn_angle: float = -math.pi / 2
    goal: np.ndarray = field(default_factory=lambda: np.array([WIDTH/2, 100], dtype=np.float32))
    bg_color: tuple = (0.086, 0.117, 0.25)
    accent_color: tuple = (0.43, 0.82, 1.0)
    player_color: tuple = (1.0, 0.92, 0.43)
    boxes: List[BoxShape] = field(default_factory=list)
    circles: List[CircleShape] = field(default_factory=list)
    lasers: List[Dict] = field(default_factory=list)
    orbs: List[np.ndarray] = field(default_factory=list)
    checkpoints: List[np.ndarray] = field(default_factory=list)
    moving_shapes: List[MovingShape] = field(default_factory=list)

class LevelLoader:
    @staticmethod
    def from_dict(data: Dict[str, Any]) -> LevelData:
        lvl = LevelData(name=data.get("name", "Custom Zone"))
        lvl.spawn = np.array(data.get("spawn", [WIDTH/2, HEIGHT-100]), dtype=np.float32)
        lvl.spawn_angle = float(data.get("spawn_angle", -math.pi / 2))
        lvl.goal = np.array(data.get("goal", [WIDTH/2, 100]), dtype=np.float32)
        lvl.bg_color = tuple(data.get("bg_color", [0.086, 0.117, 0.25]))
        lvl.accent_color = tuple(data.get("accent_color", [0.43, 0.82, 1.0]))
        lvl.player_color = tuple(data.get("player_color", [1.0, 0.92, 0.43]))

        def parse_shape(s, cls, pos_key="pos"):
            kwargs = {
                'center': np.array(s[pos_key], dtype=np.float32),
                'color': tuple(s.get("color", lvl.accent_color)),
                'bounce': float(s.get("bounce", 0.0)),
            }
            if cls == BoxShape:
                kwargs['half_size'] = np.array(s["size"], dtype=np.float32) / 2.0
                kwargs['rot_speed'] = float(s.get("rot_speed", 0.0))
            else:
                kwargs['radius'] = float(s.get("radius", 30.0))
            return cls(**kwargs)

        for b in data.get("boxes", []):
            lvl.boxes.append(parse_shape(b, BoxShape))
        for c in data.get("circles", []):
            lvl.circles.append(parse_shape(c, CircleShape))

        for ms in data.get("moving_shapes", []):
            base_shape = parse_shape(ms, BoxShape if "size" in ms else CircleShape, pos_key="pos1")
            lvl.moving_shapes.append(MovingShape(
                shape=base_shape,
                motion_type=ms.get("motion_type", "linear"),
                pos1=np.array(ms.get("pos1", [0,0]), dtype=np.float32),
                pos2=np.array(ms.get("pos2", [0,0]), dtype=np.float32),
                center=np.array(ms.get("center", [0,0]), dtype=np.float32),
                radius=float(ms.get("radius", 50.0)),
                speed=float(ms.get("speed", 1.0)),
                phase=float(ms.get("phase", 0.0))
            ))

        for l in data.get("lasers", []):
            lvl.lasers.append({
                "center": np.array(l["pos"], dtype=np.float32),
                "speed": float(l.get("speed", 1.0)),
                "length": float(l.get("length", 100.0)),
                "phase": float(l.get("phase", 0.0))
            })
        for o in data.get("orbs", []):
            lvl.orbs.append(np.array([o[0], o[1], 10.0], dtype=np.float32))
        for cp in data.get("checkpoints", []):
            r = cp[2] if len(cp) > 2 else 22.0
            lvl.checkpoints.append(np.array([cp[0], cp[1], r], dtype=np.float32))

        return lvl

    @staticmethod
    def update(level: LevelData, t):
        for ms in level.moving_shapes:
            ms.update(t)

    @staticmethod
    def evaluate_sdf(level: LevelData, p, t):
        if p[0] < 0 or p[0] > WIDTH or p[1] < 0 or p[1] > HEIGHT:
            return -10.0, False, None
        d = 1e9
        hit_obj = None

        for b in level.boxes:
            bd = sd_box(p, b.center, b.half_size, b.rot)
            if bd < d: d = bd; hit_obj = b
        for c in level.circles:
            cd = sd_circle(p, c.center, c.radius)
            if cd < d: d = cd; hit_obj = c
        for ms in level.moving_shapes:
            if isinstance(ms.shape, BoxShape):
                bd = sd_box(p, ms.shape.center, ms.shape.half_size, ms.shape.rot)
                if bd < d: d = bd; hit_obj = ms.shape
            else:
                cd = sd_circle(p, ms.shape.center, ms.shape.radius)
                if cd < d: d = cd; hit_obj = ms.shape

        hazard_d = 1e9
        for l in level.lasers:
            ang = t * l["speed"] + l["phase"]
            dir_vec = np.array([math.cos(ang), math.sin(ang)], dtype=np.float32) * l["length"]
            hazard_d = min(hazard_d, sd_segment(p, l["center"] - dir_vec, l["center"] + dir_vec, 6.0))

        if hazard_d < d:
            return hazard_d, True, None
        return d, False, hit_obj

    @staticmethod
    def normal_at(level: LevelData, p, t, eps=2.0):
        d0, _, _ = LevelLoader.evaluate_sdf(level, p, t)
        dx, _, _ = LevelLoader.evaluate_sdf(level, p + np.array([eps, 0], dtype=np.float32), t)
        dy, _, _ = LevelLoader.evaluate_sdf(level, p + np.array([0, eps], dtype=np.float32), t)
        n = np.array([dx - d0, dy - d0], dtype=np.float32)
        l = float(np.linalg.norm(n))
        return n / l if l > 1e-6 else np.array([0.0, -1.0], dtype=np.float32)
