# Deadlock Meta Tracker 🔒🎮

A Discord bot built with `nextcord` that tracks hero tier lists and build recommendations for Deadlock from [Tracklock.gg](https://tracklock.gg), alongside custom community builds defined in a local JSON file.

## Description 📜

The bot scrapes real-time hero analytics and build statistics directly from Tracklock, serving them inside Discord via slash commands. It automatically caches web responses with a configurable Time-To-Live (TTL) to deliver fast results and reduce external network requests. Additionally, it supports a custom mapping file (`build_ids.json`) that allows server administrators or players to link custom in-game build IDs alongside official Tracklock builds.

The bot performs the following operations:

1. **Tier List Tracking:** Scrapes and parses the latest hero rankings, win rates, and pick rates from Tracklock's tier list page, presenting them in formatted ASCII tables across Discord embeds.


2. **Build Extraction:** Fetches official Tracklock recommended builds, win rates, and match counts for any specified hero.


3. **Custom Build Integration:** Reads `build_ids.json` to merge custom community build IDs with official Tracklock builds for easy copy-pasting into the game client.


4. **Smart Caching & Error Handling:** Utilizes an in-memory TTL cache for web requests and gracefully falls back to cached data if network requests fail.



## Features ✨

* **`/tierlist` Slash Command:** Displays current hero tiers (S+ to D), win rates, and pick rates formatted in clean monospace tables.


* **`/build` Slash Command:** Displays recommended builds, match statistics, official Tracklock build IDs, and extra custom build IDs for any hero.


* **Custom Builds Storage:** Map custom build names and game IDs to heroes in `build_ids.json`.


* **Hero Alias Resolution:** Automatically handles hero name queries and common aliases (e.g., `geist` -> `lady-geist`, `7` -> `seven`).



## Custom Builds Mapping (`build_ids.json`) 🛠️

You can add custom community builds by editing `build_ids.json`. The bot parses `"tracklock"` as the primary build ID and treats any additional key-value pairs as custom community builds:

```json
{
  "victor": {
    "tracklock": "317850",
    "heresy": "511238",
    "apacycle gun": "611933",
    "apacycle spirit": "352387"
  },
  "apollo": {
    "tracklock": "469013",
    "oses": "353960"
  }
}

```

## How to use 🚀

1. **Prerequisites:** Make sure you have Python 3.10+ installed on your system or VPS. Install all required dependencies using `requirements.txt`:


```bash
pip install -r requirements.txt

```


2. **Environment Configuration:** Create a `.env` file in the root directory (or copy from `.env.example`) and supply your Discord Bot Token and optional configuration settings:


```env
DISCORD_TOKEN=your_discord_bot_token_here
CACHE_TTL_SECONDS=900
BUILD_IDS_FILE=build_ids.json

```


3. **Navigate to the script directory:** Open your terminal and navigate to the project folder:


```bash
cd tracklock-bot

```


4. **Run the Bot:** Execute the main script to launch the bot:


```bash
python bot.py

```



## Available Commands 🤖

* **`/tierlist`** — Displays the current Deadlock hero tier list sorted by tier and win rate.


* **`/build hero:<hero_name>`** — Displays official Tracklock builds and custom build IDs for the specified hero (e.g., `/build hero:victor` or `/build hero:haze`).



## License 📄

This project is licensed under the [MIT License](https://www.google.com/search?q=LICENSE).

Made with ❤️ by Texdroid
