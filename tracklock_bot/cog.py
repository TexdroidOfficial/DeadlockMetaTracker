from __future__ import annotations

import logging
from typing import cast

import nextcord
from nextcord import Interaction, SlashOption
from nextcord.ext import commands

from .formatter import chunk_codeblock_table, format_build_table, format_timestamp, format_tier_table
from .models import BuildRow, TierRow
from .tracklock_client import DataEnvelope, TracklockClient, TracklockError


LOGGER = logging.getLogger(__name__)


class TracklockCog(commands.Cog):
    def __init__(self, bot: commands.Bot, client: TracklockClient) -> None:
        self.bot = bot
        self.client = client

    @nextcord.slash_command(description="Show the current Tracklock hero tier list")
    async def tierlist(self, interaction: Interaction) -> None:
        await interaction.response.defer()

        try:
            envelope = self.client.fetch_tierlist()
        except TracklockError as exc:
            await interaction.followup.send(f"Could not fetch tier list right now: {exc}")
            return

        rows = cast(list[TierRow], envelope.rows)
        table = format_tier_table(rows)
        chunks = chunk_codeblock_table(table)

        embeds: list[nextcord.Embed] = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            title = "Deadlock Tier List"
            if total > 1:
                title += f" ({idx}/{total})"

            embed = nextcord.Embed(
                title=title,
                description=chunk,
                color=nextcord.Color.blurple(),
            )
            embed.set_footer(
                text=self._footer(envelope, "tracklock.gg/heroes-tier-list")
            )
            embeds.append(embed)

        await interaction.followup.send(embeds=embeds)

    @nextcord.slash_command(description="Show available Tracklock builds for a hero")
    async def build(
        self,
        interaction: Interaction,
        hero: str = SlashOption(description="Hero name, e.g. victor", required=True),
    ) -> None:
        await interaction.response.defer()

        try:
            envelope = self.client.fetch_builds(hero)
        except TracklockError as exc:
            await interaction.followup.send(f"Could not fetch builds right now: {exc}")
            return

        rows = cast(list[BuildRow], envelope.rows)
        if not rows:
            await interaction.followup.send("No builds found for that hero.")
            return

        table = format_build_table(rows)
        hero_name = rows[0].hero_name
        builds_url = rows[0].hero_builds_url
        tracklock_ids = " ".join(
            f"`{row.game_build_id}`" for row in rows if row.build_type == "tracklock" and row.game_build_id
        )
        custom_ids = " ".join(
            f"`{row.game_build_id}`" for row in rows if row.build_type == "custom" and row.game_build_id
        )
        chunks = chunk_codeblock_table(table)

        embeds: list[nextcord.Embed] = []
        total = len(chunks)
        for idx, chunk in enumerate(chunks, start=1):
            title = f"{hero_name} Builds"
            if total > 1:
                title += f" ({idx}/{total})"
            embed = nextcord.Embed(
                title=title,
                description=chunk,
                color=nextcord.Color.green(),
                url=builds_url,
            )
            if idx == 1 and tracklock_ids:
                embed.add_field(name="Tracklock Build ID", value=tracklock_ids, inline=False)
            if idx == 1 and custom_ids:
                embed.add_field(name="Extra Build IDs", value=custom_ids, inline=False)
            embed.add_field(name="Tracklock Page", value=f"[Open builds tab]({builds_url})", inline=False)
            embed.set_footer(text=self._footer(envelope, builds_url.replace("https://", "")))
            embeds.append(embed)

        await interaction.followup.send(embeds=embeds)

    @staticmethod
    def _footer(envelope: DataEnvelope, source: str) -> str:
        stale_txt = " (stale cache)" if envelope.stale else ""
        return f"Source: {source} | Updated: {format_timestamp(envelope.fetched_at)}{stale_txt}"


def setup(bot: commands.Bot, client: TracklockClient) -> None:
    bot.add_cog(TracklockCog(bot, client))
    LOGGER.info("Tracklock cog loaded")
