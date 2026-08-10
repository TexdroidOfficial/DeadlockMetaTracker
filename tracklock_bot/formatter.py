from __future__ import annotations

from datetime import datetime, timezone

from .models import BuildRow, TierRow


def _fit(text: str, width: int) -> str:
    if len(text) <= width:
        return text.ljust(width)
    if width <= 1:
        return text[:width]
    return (text[: width - 1] + "~")


def _pct(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2f}%"


def format_tier_table(rows: list[TierRow]) -> str:
    headers = ("Tier", "Hero", "Win Rate", "Pick Rate")
    tier_w = max(len(headers[0]), max((len(r.tier) for r in rows), default=4))
    hero_w = max(len(headers[1]), min(18, max((len(r.hero_name) for r in rows), default=4)))
    win_w = len(headers[2])
    pick_w = len(headers[3])

    lines = [
        f"{headers[0].ljust(tier_w)}  {headers[1].ljust(hero_w)}  {headers[2].rjust(win_w)}  {headers[3].rjust(pick_w)}"
    ]

    for row in rows:
        lines.append(
            f"{row.tier.ljust(tier_w)}  {_fit(row.hero_name, hero_w)}  {_pct(row.win_rate).rjust(win_w)}  {_pct(row.pick_rate).rjust(pick_w)}"
        )

    return "\n".join(lines)


def format_build_table(rows: list[BuildRow]) -> str:
    headers = ("Build#", "Game ID", "Build", "Win Rate", "Matches")
    build_num_w = max(len(headers[0]), max((len(str(r.build_number)) for r in rows), default=6))
    game_id_w = max(len(headers[1]), max((len(r.game_build_id or "N/A") for r in rows), default=7))
    name_w = max(len(headers[2]), min(26, max((len(r.build_name) for r in rows), default=5)))
    win_w = len(headers[3])
    matches_w = len(headers[4])

    lines = [
        f"{headers[0].ljust(build_num_w)}  {headers[1].ljust(game_id_w)}  {headers[2].ljust(name_w)}  {headers[3].rjust(win_w)}  {headers[4].rjust(matches_w)}"
    ]

    for row in rows:
        match_txt = "N/A" if row.matches is None else str(row.matches)
        game_id_txt = row.game_build_id or "N/A"
        lines.append(
            f"{str(row.build_number).ljust(build_num_w)}  {game_id_txt.ljust(game_id_w)}  {_fit(row.build_name, name_w)}  {_pct(row.win_rate).rjust(win_w)}  {match_txt.rjust(matches_w)}"
        )

    return "\n".join(lines)


def chunk_codeblock_table(table: str, max_chunk_chars: int = 3600) -> list[str]:
    lines = table.splitlines()
    if not lines:
        return ["```\n```"]

    header = lines[0]
    chunks: list[str] = []
    current = [header]
    current_len = len(header)

    for line in lines[1:]:
        additional = 1 + len(line)
        if current_len + additional > max_chunk_chars and len(current) > 1:
            chunks.append("```\n" + "\n".join(current) + "\n```")
            current = [header, line]
            current_len = len(header) + 1 + len(line)
            continue

        current.append(line)
        current_len += additional

    if current:
        chunks.append("```\n" + "\n".join(current) + "\n```")

    return chunks


def format_timestamp(unix_ts: float) -> str:
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M UTC")
