"""Per-event metric models: expected goals and pass difficulty.

The xG model is the Stats Engine's own estimate from shot location only. It does not
know the simulator's hidden finishing skill, exactly like a real xG model.
"""

from __future__ import annotations

import math

from ..util import clamp

X_M = 105 / 100
Y_M = 68 / 100
BIG_CHANCE_XG = 0.3


def shot_geometry(x: float, y: float) -> tuple[float, float]:
    """Distance (m) to goal centre and angle (rad) subtended by the goal mouth."""
    dx = (100 - x) * X_M
    dy = (y - 50) * Y_M
    dist = math.hypot(dx, dy)
    a = math.atan2(7.32 * dx, dx * dx + dy * dy - 3.66**2)
    if a < 0:
        a += math.pi
    return dist, a


def xg(x: float, y: float, body_part: str = "foot") -> float:
    dist, angle = shot_geometry(x, y)
    z = -1.05 - 0.1 * dist + 1.45 * angle - (0.8 if body_part == "head" else 0.0)
    return round(clamp(1 / (1 + math.exp(-z)), 0.01, 0.95), 3)


def pass_difficulty(length_m: float, pressured: bool, x: float, end_x: float) -> float:
    """0-10 rating: longer, pressured, progressive passes into the box are harder."""
    d = 1.5 + 0.09 * length_m
    d += 2.0 if pressured else 0.0
    d += 1.8 if end_x > 83 else (0.8 if end_x > 66 else 0.0)
    d += 1.0 if end_x - x > 15 else 0.0
    return round(clamp(d, 0, 10), 1)


def in_box(x: float, y: float) -> bool:
    return x >= 83 and 21 <= y <= 79
