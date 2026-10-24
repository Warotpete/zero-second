"""Small helpers shared across modules."""

from __future__ import annotations

import math
import random


def clock(seconds: float) -> str:
    """Format match seconds as mm:ss (e.g. 4330 -> '72:10')."""
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def minute_label(seconds: float) -> str:
    """Football minute label: the 1st minute is 0:00-0:59 -> 1'."""
    return f"{int(seconds // 60) + 1}'"


def initials(name: str) -> str:
    parts = [p for p in name.replace(".", " ").split() if p]
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def short_name(name: str) -> str:
    """'Kai Mendes' -> 'K. Mendes'."""
    parts = name.split()
    if len(parts) < 2:
        return name
    return f"{parts[0][0]}. {' '.join(parts[1:])}"


def poisson_pmf(k: int, mu: float) -> float:
    if mu <= 0:
        return 1.0 if k == 0 else 0.0
    return math.exp(-mu) * mu**k / math.factorial(k)


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def make_rng(seed: int, *salt: object) -> random.Random:
    """Deterministic sub-generator so each component is reproducible on its own."""
    return random.Random(f"{seed}:" + ":".join(str(s) for s in salt))


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))
