from __future__ import annotations

import json
from pathlib import Path


class BuildIdStore:
    def __init__(self, file_path: str | Path) -> None:
        self.file_path = Path(file_path)
        self._data: dict[str, dict[str, str]] = {}
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

        normalized: dict[str, dict[str, str]] = {}
        for hero_slug, mapping in loaded.items():
            if not isinstance(hero_slug, str) or not isinstance(mapping, dict):
                continue

            slug = hero_slug.strip().lower()
            per_hero: dict[str, str] = {}
            for build_number, game_id in mapping.items():
                build_key = str(build_number).strip()
                game_id_val = str(game_id).strip() if game_id is not None else ""
                per_hero[build_key] = game_id_val

            normalized[slug] = per_hero

        self._data = normalized

    def get_game_build_id(self, hero_slug: str, build_number: int) -> str | None:
        hero_map = self._data.get(hero_slug.strip().lower())
        if not hero_map:
            return None

        value = hero_map.get(str(build_number))
        if value is None:
            return None

        return value or None
