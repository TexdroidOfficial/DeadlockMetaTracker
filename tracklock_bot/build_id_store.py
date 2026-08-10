from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class HeroBuildIds:
    tracklock_id: str | None
    extras: list[tuple[str, str]]


class BuildIdStore:
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self._data: dict[str, HeroBuildIds] = {}
        self.reload()

    def reload(self) -> None:
        if not self.file_path.exists():
            self._data = {}
            return

        content = self.file_path.read_text(encoding="utf-8").strip()
        if not content:
            self._data = {}
            return

        loaded = json.loads(content)
        if not isinstance(loaded, dict):
            self._data = {}
            return

        normalized: dict[str, HeroBuildIds] = {}
        for hero_slug, mapping in loaded.items():
            if not isinstance(hero_slug, str) or not isinstance(mapping, dict):
                continue

            slug = self._normalize_slug(hero_slug)
            tracklock_id: str | None = None
            extras: list[tuple[str, str]] = []

            for name, game_id in mapping.items():
                if not isinstance(name, str):
                    continue
                game_id_val = str(game_id).strip() if game_id is not None else ""
                if not game_id_val:
                    continue

                key = name.strip().lower()
                if key == "tracklock":
                    tracklock_id = game_id_val
                    continue

                extras.append((name.strip(), game_id_val))

            normalized[slug] = HeroBuildIds(tracklock_id=tracklock_id, extras=extras)

        self._data = normalized

    def get_ids(self, hero_slug: str) -> HeroBuildIds:
        slug = self._normalize_slug(hero_slug)
        found = self._data.get(slug)
        if found:
            return found

        alias_lookup = {
            "the-doorman": "doorman",
            "doorman": "the-doorman",
            "mo-and-krill": "mo-krill",
            "mo-krill": "mo-and-krill",
        }
        alias = alias_lookup.get(slug)
        if alias and alias in self._data:
            return self._data[alias]

        return HeroBuildIds(tracklock_id=None, extras=[])

    @staticmethod
    def _normalize_slug(value: str) -> str:
        return value.strip().lower()
