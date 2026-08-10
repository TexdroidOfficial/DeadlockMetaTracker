from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .build_id_store import BuildIdStore, HeroBuildIds
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
        ids = self._resolve_game_ids(hero_slug)

        build_names = self._extract_build_names(html, soup, hero_slug)
        rows: list[BuildRow] = []
        for index, build_number in enumerate(sorted(build_names.keys()), start=1):
            tracklock_id = ids.tracklock_id if index == 1 else None
            build_wr, build_matches = self._fetch_build_summary_stats(hero_slug, build_number)
            rows.append(
                BuildRow(
                    hero_name=hero_name,
                    hero_slug=hero_slug,
                    build_number=build_number,
                    game_build_id=tracklock_id,
                    build_name=build_names[build_number],
                    build_type="tracklock",
                    win_rate=build_wr,
                    matches=build_matches,
                    hero_builds_url=hero_builds_url,
                )
            )

        for custom_name, custom_id in ids.extras:
            rows.append(
                BuildRow(
                    hero_name=hero_name,
                    hero_slug=hero_slug,
                    build_number=None,
                    game_build_id=custom_id,
                    build_name=custom_name,
                    build_type="custom",
                    win_rate=None,
                    matches=None,
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

    def _extract_build_names(self, html: str, soup: BeautifulSoup, hero_slug: str) -> dict[int, str]:
        result = self._extract_build_names_from_payload(html)
        if result:
            return result

        result = {}
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href", "")
            match = BUILD_QUERY_RE.search(href)
            if match is None or match.group("slug") != hero_slug:
                continue

            label_node = anchor.find("div", class_=re.compile(r"text-sm"))
            if label_node is not None:
                text = label_node.get_text(" ", strip=True)
            else:
                text = anchor.get_text(" ", strip=True)
            text = re.sub(r"\s+", " ", text)
            text = re.sub(r"^Recommended\s*:\s*", "", text, flags=re.IGNORECASE)
            if not text:
                continue
            if re.fullmatch(r"[0-9\s.,-]+", text):
                continue

            num = int(match.group("num"))
            result[num] = text

        return result

    def _extract_build_names_from_payload(self, html: str) -> dict[int, str]:
        payload_match = re.search(r'buildsInfo\\":\[(.*?)\],\\"currentBuildQuery', html, flags=re.DOTALL)
        if payload_match is None:
            return {}

        payload = payload_match.group(1)
        found: dict[int, str] = {}
        for number_text, label in re.findall(r'buildNumber\\":(\d+),\\"label\\":\\"(.*?)\\"', payload):
            text = label.encode("utf-8").decode("unicode_escape")
            text = re.sub(r"\s+", " ", text).strip()
            text = re.sub(r"^Recommended\s*:\s*", "", text, flags=re.IGNORECASE)
            if not text or re.fullmatch(r"[0-9\s.,-]+", text):
                continue
            found[int(number_text)] = text

        return found

    def _fetch_build_summary_stats(self, hero_slug: str, build_number: int) -> tuple[float | None, int | None]:
        try:
            html = self._get_html(f"/heroes/{hero_slug}/build?build={build_number}")
        except Exception as exc:
            LOGGER.debug("Could not fetch summary for %s build %s: %s", hero_slug, build_number, exc)
            return None, None

        return self._extract_summary_stats_from_html(html)

    def _extract_summary_stats_from_html(self, html: str) -> tuple[float | None, int | None]:
        text = BeautifulSoup(html, "html.parser").get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text)

        wr_match = re.search(r"(\d{1,2}(?:\.\d+)?)\s*%\s*WR", text, flags=re.IGNORECASE)
        matches_match = re.search(r"\(\s*([\d,]+)\s*Matches\s*\)", text, flags=re.IGNORECASE)

        win_rate: float | None = None
        matches: int | None = None

        if wr_match:
            try:
                win_rate = float(wr_match.group(1))
            except ValueError:
                win_rate = None

        if matches_match:
            try:
                matches = int(matches_match.group(1).replace(",", ""))
            except ValueError:
                matches = None

        return win_rate, matches

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
            "viper": "vyper",
            "doorman": "the-doorman",
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

    def _resolve_game_ids(self, hero_slug: str) -> HeroBuildIds:
        if self.build_id_store is None:
            return HeroBuildIds(tracklock_id=None, extras=[])
        return self.build_id_store.get_ids(hero_slug)
