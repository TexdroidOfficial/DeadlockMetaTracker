from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class TierRow:
    tier: str
    hero_name: str
    hero_slug: str
    win_rate: float
    pick_rate: float


@dataclass(slots=True)
class BuildRow:
    hero_name: str
    hero_slug: str
    build_number: int
    game_build_id: str | None
    build_name: str
    win_rate: float | None
    matches: int | None
    hero_builds_url: str
