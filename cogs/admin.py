"""
cogs/admin.py — Admin/maintenance slash commands.

/train_rebuild  — force-rebuild global schedule for a year
/train_reset    — clear delivery log for a guild+year (testing)
/train_sendnow  — immediately fire a specific job to this guild's channel
/train_dbinfo   — database stats
/train_guilds   — list all registered guilds
"""

import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timezone
import logging

from utils.db import (
    get_all_guilds, get_guild_config, reset_delivery_log,
    count_delivered, get_all_jobs_for_year, get_stop, mark_delivered
)
from utils.stops_data import (
    build_schedule_for_year, seed_stops,
    format_pre_train_message, format_stop_message, format_post_train_message
)

log = logging.getLogger("new_year_train.admin")


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ------------------------------------------------------------------
    # /train_rebuild
    # ------------------------------------------------------------------

    @app_commands.command(name="train_rebuild",
                          description="Force-rebuild the global schedule for a given year.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(year="Year to rebuild (e.g. 2027)")
    async def train_rebuild(self, interaction: discord.Interaction, year: int):
        await interaction.response.defer(ephemeral=True)
        seed_stops()
        build_schedule_for_year(year, force=True)
        await interaction.followup.send(f"✅ Schedule rebuilt for **{year}**.", ephemeral=True)
        log.info(f"[guild={interaction.guild_id}] Rebuild {year} by {interaction.user}")

    # ------------------------------------------------------------------
    # /train_reset  — clear delivery log for this guild+year
    # ------------------------------------------------------------------

    @app_commands.command(name="train_reset",
                          description="Reset sent history for this server (for testing).")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(year="Year to reset delivery log for")
    async def train_reset(self, interaction: discord.Interaction, year: int):
        gid = interaction.guild_id
        reset_delivery_log(gid, year)
        await interaction.response.send_message(
            f"♻️ Delivery log cleared for **{year}** in this server. "
            f"All jobs will re-fire on schedule.", ephemeral=True
        )
        log.warning(f"[guild={gid}] Delivery log reset for {year} by {interaction.user}")

    # ------------------------------------------------------------------
    # /train_sendnow  — manually fire a job to this guild's channel
    # ------------------------------------------------------------------

    @app_commands.command(name="train_sendnow",
                          description="Immediately send a specific job to this server's channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(
        year="Target year",
        job_type="e.g. pre_train  |  stop_11  |  post_train"
    )
    async def train_sendnow(self, interaction: discord.Interaction, year: int, job_type: str):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        cfg = get_guild_config(gid)

        if not cfg or not cfg["channel_id"]:
            await interaction.followup.send(
                "❌ No channel configured. Run `/train_setup` first.", ephemeral=True
            )
            return

        channel = self.bot.get_channel(int(cfg["channel_id"]))
        if not channel:
            await interaction.followup.send("❌ Configured channel not found.", ephemeral=True)
            return

        jobs = get_all_jobs_for_year(year)
        job = next((j for j in jobs if j["job_type"] == job_type), None)
        if not job:
            await interaction.followup.send(
                f"❌ Job `{job_type}` not found for {year}.", ephemeral=True
            )
            return

        msg = self._build_message(job, year)
        if not msg:
            await interaction.followup.send("❌ Could not build message.", ephemeral=True)
            return

        await channel.send(msg)
        mark_delivered(gid, job["id"], datetime.now(timezone.utc).isoformat())
        await interaction.followup.send(
            f"✅ Sent `{job_type}` ({year}) to {channel.mention}.", ephemeral=True
        )
        log.info(f"[guild={gid}] Manual send: {job_type} ({year}) by {interaction.user}")

    # ------------------------------------------------------------------
    # /train_dbinfo
    # ------------------------------------------------------------------

    @app_commands.command(name="train_dbinfo",
                          description="Show database statistics.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def train_dbinfo(self, interaction: discord.Interaction):
        from utils.db import get_conn
        with get_conn() as conn:
            stops    = conn.execute("SELECT COUNT(*) as c FROM train_stops").fetchone()["c"]
            jobs     = conn.execute("SELECT COUNT(*) as c FROM scheduled_jobs").fetchone()["c"]
            guilds   = conn.execute("SELECT COUNT(*) as c FROM guild_config").fetchone()["c"]
            active   = conn.execute("SELECT COUNT(*) as c FROM guild_config WHERE enabled=1").fetchone()["c"]
            deliveries = conn.execute("SELECT COUNT(*) as c FROM delivery_log").fetchone()["c"]
            years    = conn.execute("SELECT DISTINCT year FROM scheduled_jobs ORDER BY year").fetchall()

        embed = discord.Embed(title="🗄️ DB Info", colour=0xffaa00)
        embed.add_field(name="Stops",         value=str(stops),     inline=True)
        embed.add_field(name="Scheduled jobs", value=str(jobs),      inline=True)
        embed.add_field(name="Total guilds",  value=str(guilds),    inline=True)
        embed.add_field(name="Active guilds", value=str(active),    inline=True)
        embed.add_field(name="Deliveries",    value=str(deliveries), inline=True)
        embed.add_field(name="Years in DB",
                        value=", ".join(str(r["year"]) for r in years) or "none",
                        inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /train_guilds
    # ------------------------------------------------------------------

    @app_commands.command(name="train_guilds",
                          description="List all guilds registered with the bot.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def train_guilds(self, interaction: discord.Interaction):
        guilds = get_all_guilds()
        if not guilds:
            await interaction.response.send_message("No guilds registered yet.", ephemeral=True)
            return

        now = datetime.now(timezone.utc)
        upcoming_year = now.year + 1 if now.month >= 11 else now.year

        lines = []
        for g in guilds:
            state   = "✅" if g["enabled"] else "⏸️"
            channel = f"<#{g['channel_id']}>" if g["channel_id"] else "*no channel*"
            delivered = count_delivered(int(g["guild_id"]), upcoming_year)
            total = len(get_all_jobs_for_year(upcoming_year))
            dg = self.bot.get_guild(int(g["guild_id"]))
            name = dg.name if dg else f"ID:{g['guild_id']}"
            lines.append(f"{state} **{name}** — {channel} — {delivered}/{total} sent")

        embed = discord.Embed(
            title=f"🚂 Registered Guilds ({len(guilds)})",
            description="\n".join(lines),
            colour=0x9900ff
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # Internal helper
    # ------------------------------------------------------------------

    def _build_message(self, job, year: int) -> str | None:
        jtype = job["job_type"]
        if jtype == "pre_train":
            return format_pre_train_message(year)
        if jtype == "post_train":
            return format_post_train_message(year)
        if jtype.startswith("stop_"):
            stop = get_stop(job["stop_number"])
            if not stop:
                return None
            return format_stop_message(
                stop["stop_number"], stop["stop_label"], stop["clock_emoji"],
                stop["locations_text"], year, stop["utc_offset_mins"]
            )
        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
