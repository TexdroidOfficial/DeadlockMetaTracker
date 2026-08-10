from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .build_id_store import BuildIdStore
from .cache import TTLCache
from .models import BuildRow, TierRow


LOGGER = logging.getLogger(__name__)


BASE_URL = "https://tracklock.gg"
TIERLIST_PATH = "/heroes-tier-list"

TIER_ORDER = {"S+": 0, "S": 1, "A+": 2, "A": 3, "B": 4, "C": 5, "D": 6}
TIER_TOKEN_RE = re.compile(r"^(S\+|S|A\+|A|B|C|D)$")
PERCENT_TOKEN_RE = re.compile(r"^(\d{1,2}\.\d{2})%$")
BUILD_QUERY_RE = re.compile(r"/heroes/(?P<slug>[a-z0-9-]+)/build\?build=(?P<num>\d+)")


class TracklockError(RuntimeError):
    pass


@dataclass(slots=True)
class DataEnvelope:
    rows: list[Any]
    fetched_at: float
    stale: bool


class TracklockClient:
    def __init__(
        self,
        cache_ttl_seconds: int = 900,
        timeout_seconds: int = 20,
        build_id_store: BuildIdStore | None = None,
    ) -> None:
        self.timeout_seconds = timeout_seconds
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/127.0.0.0 Safari/537.36"
                )
            }
        )
        self.tier_cache: TTLCache[list[TierRow]] = TTLCache(cache_ttl_seconds)
        self.build_cache: TTLCache[list[BuildRow]] = TTLCache(cache_ttl_seconds)
        self.build_id_store = build_id_store

    def fetch_tierlist(self) -> DataEnvelope:
        cache_key = "tierlist"
        fresh = self.tier_cache.get_fresh(cache_key)
        if fresh:
            return DataEnvelope(rows=fresh.value, fetched_at=fresh.fetched_at, stale=False)

        try:
            html = self._get_html(TIERLIST_PATH)
            rows = self._parse_tierlist_html(html)
            if not rows:
                raise TracklockError("No tier rows parsed from source")
            entry = self.tier_cache.set(cache_key, rows)
            return DataEnvelope(rows=entry.value, fetched_at=entry.fetched_at, stale=False)
        except Exception as exc:
            LOGGER.warning("Tierlist fetch failed: %s", exc)
            stale = self.tier_cache.get_any(cache_key)
            if stale:
                return DataEnvelope(rows=stale.value, fetched_at=stale.fetched_at, stale=True)
            raise TracklockError("Unable to fetch tier list and no cached copy available") from exc

    def fetch_builds(self, hero_query: str) -> DataEnvelope:
        canonical_slug = self._hero_query_to_slug(hero_query)
        cache_key = f"builds:{canonical_slug}"

        fresh = self.build_cache.get_fresh(cache_key)
        if fresh:
            return DataEnvelope(rows=fresh.value, fetched_at=fresh.fetched_at, stale=False)

        try:
            path = f"/heroes/{canonical_slug}/build"
            html = self._get_html(path)
            rows = self._parse_builds_html(html, canonical_slug)
            if not rows:
                raise TracklockError("No builds found for hero")
            entry = self.build_cache.set(cache_key, rows)
            return DataEnvelope(rows=entry.value, fetched_at=entry.fetched_at, stale=False)
        except Exception as exc:
            LOGGER.warning("Build fetch failed for %s: %s", canonical_slug, exc)
            stale = self.build_cache.get_any(cache_key)
            if stale:
                return DataEnvelope(rows=stale.value, fetched_at=stale.fetched_at, stale=True)
            raise TracklockError(f"Unable to fetch builds for {hero_query!r}") from exc

    def _get_html(self, path: str) -> str:
        url = urljoin(BASE_URL, path)
        response = self.session.get(url, timeout=self.timeout_seconds)
        response.raise_for_status()
        return response.text

    def _parse_tierlist_html(self, html: str) -> list[TierRow]:
        soup = BeautifulSoup(html, "html.parser")
        rows: list[TierRow] = []

        for tr in soup.find_all("tr"):
            link = tr.find("a", href=re.compile(r"^/heroes/[a-z0-9-]+/probuild$"))
            if link is None:
                continue

            href = link.get("href", "")
            parts = href.strip("/").split("/")
            if len(parts) < 3:
                continue
            hero_slug = parts[1]

            hero_name = self._extract_hero_name(link)
            if not hero_name:
                continue

            tier = self._extract_tier_token(tr)
            if tier is None:
                continue

            percents = self._extract_percents_in_order(tr)
            if len(percents) < 2:
                continue

            rows.append(
                TierRow(
                    tier=tier,
                    hero_name=hero_name,
                    hero_slug=hero_slug,
                    win_rate=percents[0],
                    pick_rate=percents[1],
                )
            )

        rows.sort(key=lambda r: (TIER_ORDER.get(r.tier, 99), -r.win_rate, r.hero_name.lower()))
        return rows

    def _parse_builds_html(self, html: str, hero_slug: str) -> list[BuildRow]:
        soup = BeautifulSoup(html, "html.parser")

        hero_name = self._extract_hero_title(soup) or hero_slug.replace("-", " ").title()
        hero_builds_url = urljoin(BASE_URL, f"/heroes/{hero_slug}/build")

        build_names = self._extract_build_names(soup, hero_slug)
        summary_wr, summary_matches = self._extract_summary_wr_matches(soup)

        rows: list[BuildRow] = []
        for build_number in sorted(build_names.keys()):
            rows.append(
                BuildRow(
                    hero_name=hero_name,
                    hero_slug=hero_slug,
                    build_number=build_number,
                    game_build_id=self._resolve_game_build_id(hero_slug, build_number),
                    build_name=build_names[build_number],
                    win_rate=summary_wr.get(build_number),
                    matches=summary_matches.get(build_number),
                    hero_builds_url=hero_builds_url,
                )
            )

        return rows

    def _extract_hero_title(self, soup: BeautifulSoup) -> str | None:
        title = soup.title.string.strip() if soup.title and soup.title.string else ""
        if title and " Build" in title:
            return title.split(" Build", 1)[0].strip()

        h1 = soup.find("h1")
        if h1:
            text = h1.get_text(" ", strip=True)
            if text:
                return text

        return None

    def _extract_build_names(self, soup: BeautifulSoup, hero_slug: str) -> dict[int, str]:
        result: dict[int, str] = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            match = BUILD_QUERY_RE.search(href)
            if match is None or match.group("slug") != hero_slug:
                continue

            text = anchor.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            if not text:
                continue

            num = int(match.group("num"))
            result[num] = text

        return result

    def _extract_summary_wr_matches(self, soup: BeautifulSoup) -> tuple[dict[int, float], dict[int, int]]:
        wr_by_build: dict[int, float] = {}
        matches_by_build: dict[int, int] = {}

        text = soup.get_text("\n", strip=True)
        current_build = 1
        if "?build=2" in str(soup):
            # Best effort for multi-build pages where summary is the selected build.
            active = soup.find("a", href=re.compile(r"\?build=(\d+)"), attrs={"aria-current": "page"})
            if active:
                match = re.search(r"\?build=(\d+)", active.get("href", ""))
                if match:
                    current_build = int(match.group(1))

        wr_match = re.search(r"(\d{1,2}\.\d)%\s*WR", text)
        if wr_match:
            wr_by_build[current_build] = float(wr_match.group(1))

        matches_match = re.search(r"\((\d+)\s+Matches\)", text)
        if matches_match:
            matches_by_build[current_build] = int(matches_match.group(1))

        return wr_by_build, matches_by_build

    def _extract_hero_name(self, link: Any) -> str:
        img = link.find("img")
        if img and img.get("alt"):
            return str(img["alt"]).strip()

        text = link.get_text(" ", strip=True)
        return re.sub(r"\s+", " ", text)

    def _extract_tier_token(self, tr: Any) -> str | None:
        for span in tr.find_all("span"):
            token = span.get_text(strip=True)
            if TIER_TOKEN_RE.match(token):
                return token
        return None

    def _extract_percents_in_order(self, tr: Any) -> list[float]:
        values: list[float] = []
        for token in tr.stripped_strings:
            clean = token.replace("\u2212", "-")
            match = PERCENT_TOKEN_RE.match(clean)
            if match:
                values.append(float(match.group(1)))
        return values

    def _hero_query_to_slug(self, hero_query: str) -> str:
        query = hero_query.strip().lower()
        if not query:
            raise TracklockError("Hero name cannot be empty")

        query = re.sub(r"\s+", "-", query)
        query = re.sub(r"[^a-z0-9\-&]", "", query)

        aliases = {
            "viktor": "victor",
            "mcginnis": "mcginnis",
            "lady-geist": "lady-geist",
            "geist": "lady-geist",
            "mo-&-krill": "mo-and-krill",
            "mo-krill": "mo-and-krill",
            "grey-talon": "grey-talon",
            "talon": "grey-talon",
            "legolas": "grey-talon",
            "7": "seven",
            "gt": "grey-talon",
            "vinny": "vindicta",
        }
        return aliases.get(query, query)

    def _resolve_game_build_id(self, hero_slug: str, build_number: int) -> str | None:
        if self.build_id_store is None:
            return None
        return self.build_id_store.get_game_build_id(hero_slug, build_number)
