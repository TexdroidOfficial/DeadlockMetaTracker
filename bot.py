from __future__ import annotations

import logging
import os

import nextcord
from dotenv import load_dotenv
from nextcord.ext import commands

from tracklock_bot.build_id_store import BuildIdStore
from tracklock_bot.cog import setup as setup_cog
from tracklock_bot.tracklock_client import TracklockClient


def build_bot() -> commands.Bot:
    intents = nextcord.Intents.default()
    bot = commands.Bot(intents=intents)

    ttl = int(os.getenv("CACHE_TTL_SECONDS", "900"))
    build_id_file = os.getenv("BUILD_IDS_FILE", "build_ids.json")
    id_store = BuildIdStore(build_id_file)
    client = TracklockClient(cache_ttl_seconds=ttl, build_id_store=id_store)
    setup_cog(bot, client)

    @bot.event
    async def on_ready() -> None:
        logging.info("Logged in as %s (%s)", bot.user, bot.user.id if bot.user else "unknown")

    @bot.event
    async def on_application_command_error(
        interaction: nextcord.Interaction,
        error: Exception,
    ) -> None:
        logging.exception(
            "Application command error user=%s command=%s",
            interaction.user.id if interaction.user else "unknown",
            interaction.application_command.qualified_name if interaction.application_command else "unknown",
            exc_info=error,
        )

        if interaction.response.is_done():
            try:
                await interaction.followup.send("Something went wrong while processing that command.")
            except Exception:
                logging.exception("Failed to send followup error message")
        else:
            try:
                await interaction.response.send_message("Something went wrong while processing that command.", ephemeral=True)
            except Exception:
                logging.exception("Failed to send initial error response")

    return bot


def main() -> None:
    load_dotenv()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )

    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")

    bot = build_bot()
    bot.run(token)


if __name__ == "__main__":
    main()
