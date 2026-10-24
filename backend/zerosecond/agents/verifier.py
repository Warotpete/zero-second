"""Deterministic Verifier: every number and player name in a draft must come from the facts pack."""

from __future__ import annotations

from dataclasses import dataclass, field
import re

WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
    "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "twenty-five": 25, "thirty": 30,
    "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "seventy-five": 75, "eighty": 80, "ninety": 90,
    "hundred": 100,
}
ORDINAL_WORDS = {
    "fifth": 5, "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10, "fifteenth": 15,
    "twentieth": 20, "fiftieth": 50, "hundredth": 100,
}
# small counting words that are almost always generic prose, not statistics
GENERIC = {1, 2, 3}

NUM_RE = re.compile(r"(?<![\w.])(\d+(?:\.\d+)?)(?:st|nd|rd|th)?(?![\w])")
WORD_RE = re.compile(r"\b(" + "|".join(sorted(list(WORDS) + list(ORDINAL_WORDS), key=len, reverse=True)) + r")\b", re.I)
SLOT_RE = re.compile(r"\{([a-z_]+)\}")


@dataclass
class Check:
    ok: bool
    issues: list[str] = field(default_factory=list)
    numbers_checked: int = 0


def numbers_in(text: str) -> list[float]:
    plain = SLOT_RE.sub(" ", text)
    plain = re.sub(r"\b(MW|Matchweek|GW)(\d+)", r"\1 \2", plain)
    out = [float(m.group(1)) for m in NUM_RE.finditer(plain)]
    for m in WORD_RE.finditer(plain):
        w = m.group(1).lower()
        out.append(float(WORDS.get(w, ORDINAL_WORDS.get(w, 0))))
    return out


def allowed_numbers(facts: dict) -> set[float]:
    vals: set[float] = set()

    def add(v: object) -> None:
        if isinstance(v, bool):
            return
        if isinstance(v, (int, float)):
            vals.add(round(float(v), 2))
        elif isinstance(v, str):
            for n in NUM_RE.findall(v):
                vals.add(round(float(n), 2))
        elif isinstance(v, dict):
            for x in v.values():
                add(x)
        elif isinstance(v, (list, tuple)):
            for x in v:
                add(x)

    add(facts)
    return vals


def verify(text: str, facts: dict, known_names: dict[str, str], allowed_slots: set[str] | None = None) -> Check:
    """Check one version.

    known_names: surname -> player id for every player in the match; any surname used
    must belong to a player listed in facts["players"].
    """
    issues: list[str] = []
    allowed = allowed_numbers(facts)
    nums = numbers_in(text)
    for n in nums:
        if round(n, 2) in allowed or (n in GENERIC and n == int(n)):
            continue
        shown = int(n) if n == int(n) else n
        issues.append(f"number {shown} is not in the facts pack")
    cast = set(facts.get("players", {}).values()) if isinstance(facts.get("players"), dict) else set()
    for surname, pid in known_names.items():
        if re.search(rf"\b{re.escape(surname)}\b", text) and pid not in cast:
            issues.append(f"mentions {surname}, who is not part of this story")
    for slot in SLOT_RE.findall(text):
        if allowed_slots is not None and slot not in allowed_slots:
            issues.append(f"unknown slot {{{slot}}}")
    return Check(not issues, issues, len(nums))


def fill_slots(text: str, slots: dict[str, object]) -> str:
    return SLOT_RE.sub(lambda m: str(slots.get(m.group(1), m.group(0))), text)
