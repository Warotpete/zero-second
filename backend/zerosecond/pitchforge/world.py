"""Fictional clubs and players.

Every player carries *hidden* traits (finishing, pace, stamina ...). The match
simulator uses them to decide what happens; the Stats Engine and Story Radar never
see them, they only see events. That separation is what makes the forecast
calibration check meaningful.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import random

from ..util import initials, make_rng

CLUBS: list[tuple[str, str, str]] = [
    # (id, name, short)
    ("HFC", "Harbour City FC", "Harbour City"),
    ("NLU", "Northvale United", "Northvale"),
    ("ASH", "Ashbourne Rovers", "Ashbourne"),
    ("KMA", "Kingsmere Athletic", "Kingsmere"),
    ("RDC", "Redcliffe Town", "Redcliffe"),
    ("WBK", "Westbrook Albion", "Westbrook"),
    ("ELM", "Elmstead City", "Elmstead"),
    ("FHV", "Fairhaven FC", "Fairhaven"),
    ("STB", "Stonebridge United", "Stonebridge"),
    ("GWA", "Greywater Athletic", "Greywater"),
    ("CTW", "Castleton Wanderers", "Castleton"),
    ("HMT", "Hollowmere Town", "Hollowmere"),
    ("LDF", "Lindenfield FC", "Lindenfield"),
    ("RVP", "Ravenport United", "Ravenport"),
    ("CPH", "Copperhill City", "Copperhill"),
    ("WYC", "Wyncliffe Rovers", "Wyncliffe"),
    ("EMR", "Eastmoor FC", "Eastmoor"),
    ("BWA", "Brightwell Albion", "Brightwell"),
    ("DMA", "Dunmore Athletic", "Dunmore"),
    ("OKR", "Oakhurst Rangers", "Oakhurst"),
]

FIRST = [
    "Aaron", "Adil", "Alfie", "Amadou", "Andre", "Arlo", "Bastien", "Ben", "Callum", "Caio",
    "Dario", "Dele", "Elias", "Emre", "Ethan", "Felix", "Femi", "Finn", "Gabriel", "Hamza",
    "Hugo", "Iker", "Isaac", "Jalen", "Jonas", "Joel", "Kenji", "Kofi", "Lars", "Leon",
    "Luca", "Malik", "Marco", "Mateo", "Milan", "Nico", "Noah", "Oli", "Omar", "Oscar",
    "Pavel", "Rafa", "Rhys", "Ruben", "Sami", "Santi", "Theo", "Tomas", "Victor", "Yusuf",
]
LAST = [
    "Abara", "Albers", "Bakari", "Barros", "Bellamy", "Brandt", "Calloway", "Castell", "Dahl",
    "Delacroix", "Duarte", "Eklund", "Farrow", "Ferreira", "Galloway", "Gunnarsen", "Haddad",
    "Holm", "Ibarra", "Iwobi-Lane", "Jansen", "Kaminski", "Keane-Hart", "Lindqvist", "Lowe",
    "Marchetti", "Mensah", "Moreau", "Nakamura", "Novak", "Oduya", "Ostrowski", "Pereira",
    "Quayle", "Rahman", "Rossetti", "Sandoval", "Shaw", "Sorensen", "Tavares", "Thorne",
    "Uche", "Valente", "Vidal", "Whitlock", "Yilmaz", "Zelenko", "Ambrose", "Okonjo", "Corrigan",
]

# 4-3-3: (position, role, base x, base y) in attacking-direction coordinates 0-100.
FORMATION = [
    ("GK", "GK", 5, 50),
    ("RB", "DEF", 28, 85), ("CB", "DEF", 22, 62), ("CB", "DEF", 22, 38), ("LB", "DEF", 28, 15),
    ("CM", "MID", 45, 68), ("DM", "MID", 38, 50), ("CM", "MID", 45, 32),
    ("RW", "FWD", 70, 82), ("ST", "FWD", 78, 50), ("LW", "FWD", 70, 18),
]
SUB_ROLES = ["GK", "DEF", "MID", "FWD", "FWD"]


@dataclass
class Player:
    id: str
    name: str
    team_id: str
    number: int
    position: str
    role: str  # GK / DEF / MID / FWD
    base_x: float = 50.0
    base_y: float = 50.0
    starter: bool = True
    # hidden traits (simulator only)
    finishing: float = 1.0
    shot_weight: float = 1.0
    pace_kmh: float = 31.0
    passing: float = 1.0
    stamina: float = 1.0
    work_rate_km: float = 10.5
    keeper_skill: float = 1.0
    # public history (Season Memory)
    club_goals_before_season: int = 0
    signed_this_week: bool = False

    @property
    def initials(self) -> str:
        return initials(self.name)

    def public(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "initials": self.initials,
            "team": self.team_id,
            "number": self.number,
            "position": self.position,
            "role": self.role,
            "starter": self.starter,
        }


@dataclass
class Team:
    id: str
    name: str
    short: str
    attack: float  # expected goals per 90 vs an average side
    defense: float  # expected goals conceded per 90 vs an average side
    players: list[Player] = field(default_factory=list)

    def player(self, pid: str) -> Player:
        return next(p for p in self.players if p.id == pid)

    @property
    def starters(self) -> list[Player]:
        return [p for p in self.players if p.starter]

    @property
    def bench(self) -> list[Player]:
        return [p for p in self.players if not p.starter]

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "short": self.short}


@dataclass
class World:
    seed: int
    teams: dict[str, Team]

    def player(self, pid: str) -> Player:
        team_id = pid.split("-")[0]
        return self.teams[team_id].player(pid)

    def all_players(self) -> list[Player]:
        return [p for t in self.teams.values() for p in t.players]


def _role_traits(rng: random.Random, p: Player) -> None:
    if p.role == "FWD":
        p.finishing = rng.uniform(0.9, 1.25)
        p.shot_weight = rng.uniform(2.2, 3.6)
        p.pace_kmh = rng.uniform(32.0, 35.5)
        p.club_goals_before_season = rng.randint(0, 110)
    elif p.role == "MID":
        p.finishing = rng.uniform(0.8, 1.1)
        p.shot_weight = rng.uniform(0.8, 1.6)
        p.pace_kmh = rng.uniform(30.0, 33.5)
        p.passing = rng.uniform(1.0, 1.25)
        p.work_rate_km = rng.uniform(11.0, 12.6)
        p.club_goals_before_season = rng.randint(0, 40)
    elif p.role == "DEF":
        p.finishing = rng.uniform(0.6, 0.95)
        p.shot_weight = rng.uniform(0.25, 0.6)
        p.pace_kmh = rng.uniform(30.5, 34.0)
        p.work_rate_km = rng.uniform(10.0, 11.2)
        p.club_goals_before_season = rng.randint(0, 12)
    else:  # GK
        p.finishing = 0.3
        p.shot_weight = 0.0
        p.pace_kmh = rng.uniform(26.0, 29.0)
        p.work_rate_km = rng.uniform(5.0, 6.2)
        p.keeper_skill = rng.uniform(0.85, 1.15)
    p.stamina = rng.uniform(0.85, 1.15)


def build_world(seed: int) -> World:
    rng = make_rng(seed, "world")
    used: set[str] = set()
    teams: dict[str, Team] = {}
    for tid, name, short in CLUBS:
        attack = rng.uniform(1.05, 1.85)
        defense = rng.uniform(1.0, 1.75)
        team = Team(tid, name, short, attack, defense)
        roles = [(pos, role, x, y, True) for pos, role, x, y in FORMATION]
        roles += [(r, r, 50, 50, False) for r in SUB_ROLES]
        numbers = rng.sample(range(2, 40), len(roles))
        for i, (pos, role, x, y, starter) in enumerate(roles):
            while True:
                full = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
                if full not in used:
                    used.add(full)
                    break
            number = 1 if pos == "GK" and starter else numbers[i]
            p = Player(
                id=f"{tid}-{i:02d}",
                name=full,
                team_id=tid,
                number=number,
                position=pos if starter else role,
                role=role,
                base_x=x,
                base_y=y,
                starter=starter,
            )
            _role_traits(rng, p)
            team.players.append(p)
        new_fwd = [p for p in team.bench if p.role == "FWD"]
        if new_fwd and rng.random() < 0.3:
            new_fwd[0].signed_this_week = True
            new_fwd[0].club_goals_before_season = 0
        teams[tid] = team
    return World(seed, teams)
