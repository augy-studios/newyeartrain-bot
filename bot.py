import discord
from discord.ext import commands
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)
log = logging.getLogger("new_year_train")

intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)

COGS = ["cogs.train", "cogs.admin"]


@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} ({bot.user.id})")
    log.info(f"Serving {len(bot.guilds)} guild(s)")
    try:
        synced = await bot.tree.sync()
        log.info(f"Synced {len(synced)} slash command(s)")
    except Exception as e:
        log.error(f"Failed to sync commands: {e}")


@bot.event
async def on_guild_join(guild: discord.Guild):
    """Auto-register the guild in the DB when the bot is added."""
    from utils.db import ensure_guild
    ensure_guild(guild.id)
    log.info(f"Joined guild: {guild.name} ({guild.id})")


@bot.event
async def on_guild_remove(guild: discord.Guild):
    log.info(f"Removed from guild: {guild.name} ({guild.id})")


async def main():
    from utils.db import init_db
    from utils.stops_data import seed_stops, build_schedule_for_year
    from datetime import datetime, timezone

    init_db()
    seed_stops()

    now = datetime.now(timezone.utc)
    for year in [now.year, now.year + 1]:
        build_schedule_for_year(year)

    async with bot:
        for cog in COGS:
            try:
                await bot.load_extension(cog)
                log.info(f"Loaded: {cog}")
            except Exception as e:
                log.error(f"Failed to load {cog}: {e}")
        await bot.start(os.environ["DISCORD_TOKEN"])


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())