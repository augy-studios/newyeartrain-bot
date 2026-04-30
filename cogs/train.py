"""
cogs/train.py — Multi-guild scheduler + per-guild slash commands.

Scheduler ticks every 30s:
  - Ensures stops are seeded and schedules exist for current + next year
  - For each active guild, sends any due jobs the guild hasn't received yet
  - Skips jobs that are >3 min stale (bot was down) without sending

Per-guild stop enable/disable:
  - Absent row in guild_stop_enabled = enabled (opt-out model)
  - Admins can disable individual stops, ranges, or all non-key stops
"""

import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import asyncio

from utils.db import (
    get_guild_config, set_guild_channel, set_guild_enabled,
    get_all_active_guilds, ensure_guild,
    is_stop_enabled, set_stop_enabled, set_stop_range_enabled,
    get_disabled_stops, reset_stop_overrides,
    has_delivered, mark_delivered, count_delivered, get_stop,
    get_all_jobs_for_year, jobs_exist_for_year
)
from utils.stops_data import (
    build_schedule_for_year, seed_stops,
    format_pre_train_message, format_stop_message, format_post_train_message,
    compute_fire_utc
)

log = logging.getLogger("new_year_train.train")

MAX_LATE_SECONDS = 180  # skip if bot was down >3 min past fire time


class TrainCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._channel_cache: dict[int, discord.TextChannel] = {}
        self.scheduler_loop.start()

    def cog_unload(self):
        self.scheduler_loop.cancel()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _target_years(self, now: datetime) -> list[int]:
        """Years whose trains might need processing right now."""
        # next year's train (fires Dec 31 - Jan 1)
        # current year's train (might still be in progress on Jan 1)
        return [now.year, now.year + 1]

    async def _get_channel(self, guild_id: int, channel_id: int) -> Optional[discord.TextChannel]:
        if guild_id in self._channel_cache:
            return self._channel_cache[guild_id]
        ch = self.bot.get_channel(channel_id)
        if ch:
            self._channel_cache[guild_id] = ch
        return ch

    def _build_message(self, job, year: int) -> Optional[str]:
        jtype = job["job_type"]
        if jtype == "pre_train":
            return format_pre_train_message(year)
        if jtype == "post_train":
            return format_post_train_message(year)
        if jtype.startswith("stop_"):
            stop_num = job["stop_number"]
            stop = get_stop(stop_num)
            if not stop:
                return None
            return format_stop_message(
                stop["stop_number"], stop["stop_label"], stop["clock_emoji"],
                stop["locations_text"], year, stop["utc_offset_mins"]
            )
        return None

    # ------------------------------------------------------------------
    # Scheduler loop
    # ------------------------------------------------------------------

    @tasks.loop(seconds=30)
    async def scheduler_loop(self):
        now = datetime.now(timezone.utc)
        seed_stops()

        for year in self._target_years(now):
            if not jobs_exist_for_year(year):
                build_schedule_for_year(year)

        active_guilds = get_all_active_guilds()
        for guild_row in active_guilds:
            await self._process_guild(guild_row, now)

    @scheduler_loop.before_loop
    async def _before_loop(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(2)

    async def _process_guild(self, guild_row, now: datetime):
        guild_id   = int(guild_row["guild_id"])
        channel_id = int(guild_row["channel_id"])
        channel    = await self._get_channel(guild_id, channel_id)
        if not channel:
            self._channel_cache.pop(guild_id, None)
            return

        for year in self._target_years(now):
            jobs = get_all_jobs_for_year(year)
            for job in jobs:
                fire_dt = datetime.fromisoformat(job["fire_utc"]).replace(tzinfo=timezone.utc)
                if fire_dt > now:
                    break  # sorted by fire_utc; nothing else is due

                if has_delivered(guild_id, job["id"]):
                    continue

                # Check stop-level toggle for this guild
                if not is_stop_enabled(guild_id, job["job_type"]):
                    # Mark delivered anyway so it doesn't sit pending forever
                    mark_delivered(guild_id, job["id"], now.isoformat())
                    continue

                late = (now - fire_dt).total_seconds()
                if late > MAX_LATE_SECONDS:
                    log.warning(f"[guild={guild_id}] Skipping stale job {job['job_type']} ({year}), {late:.0f}s late")
                    mark_delivered(guild_id, job["id"], now.isoformat())
                    continue

                msg = self._build_message(job, year)
                if not msg:
                    mark_delivered(guild_id, job["id"], now.isoformat())
                    continue

                try:
                    await channel.send(msg)
                    mark_delivered(guild_id, job["id"], now.isoformat())
                    log.info(f"[guild={guild_id}] Sent {job['job_type']} ({year})")
                except discord.Forbidden:
                    log.error(f"[guild={guild_id}] No permission to send in channel {channel_id}")
                    break
                except discord.HTTPException as e:
                    log.error(f"[guild={guild_id}] HTTP error: {e}")
                    # don't mark delivered; will retry next tick

    # ------------------------------------------------------------------
    # /train_setup  — setchannel + enable in one command
    # ------------------------------------------------------------------

    @app_commands.command(name="train_setup", description="Set up the New Year Train for this server.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(channel="Channel to post New Year messages in")
    async def train_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        gid = interaction.guild_id
        ensure_guild(gid)
        set_guild_channel(gid, channel.id)
        set_guild_enabled(gid, True)
        self._channel_cache.pop(gid, None)  # bust cache
        await interaction.response.send_message(
            f"✅ New Year Train is **enabled** and will post to {channel.mention}.\n"
            f"Use `/train_toggle` to pause it at any time.",
            ephemeral=True
        )
        log.info(f"[guild={gid}] Setup: channel={channel.id}")

    # ------------------------------------------------------------------
    # /train_toggle  — on/off for the whole guild
    # ------------------------------------------------------------------

    @app_commands.command(name="train_toggle", description="Enable or disable the New Year Train for this server.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(enabled="True to enable, False to disable")
    async def train_toggle(self, interaction: discord.Interaction, enabled: bool):
        gid = interaction.guild_id
        ensure_guild(gid)
        set_guild_enabled(gid, enabled)
        state = "**enabled** ✅" if enabled else "**disabled** ⏸️"
        await interaction.response.send_message(
            f"New Year Train is now {state} for this server.", ephemeral=True
        )
        log.info(f"[guild={gid}] Toggled enabled={enabled}")

    # ------------------------------------------------------------------
    # /train_setchannel  — change channel without touching enabled state
    # ------------------------------------------------------------------

    @app_commands.command(name="train_setchannel", description="Change the posting channel (without changing enabled state).")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(channel="New channel to post in")
    async def train_setchannel(self, interaction: discord.Interaction, channel: discord.TextChannel):
        gid = interaction.guild_id
        ensure_guild(gid)
        set_guild_channel(gid, channel.id)
        self._channel_cache.pop(gid, None)
        await interaction.response.send_message(
            f"✅ Posting channel updated to {channel.mention}.", ephemeral=True
        )

    # ------------------------------------------------------------------
    # /train_stops  — enable/disable individual stops or ranges
    # ------------------------------------------------------------------

    @app_commands.command(name="train_stops",
                          description="Enable or disable specific stops (or ranges) for this server.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(
        action="enable or disable",
        stops=(
            "Comma-separated stop keys or ranges. Examples:\n"
            "  stop_11          — single stop\n"
            "  stop_1-stop_10   — range\n"
            "  pre_train        — pre-train message\n"
            "  post_train       — post-train message\n"
            "  all              — every stop + pre/post\n"
            "  all_stops        — stops 1-38 only (keeps pre/post)\n"
        )
    )
    async def train_stops(self, interaction: discord.Interaction,
                          action: str, stops: str):
        action = action.strip().lower()
        if action not in ("enable", "disable"):
            await interaction.response.send_message(
                "❌ `action` must be `enable` or `disable`.", ephemeral=True
            )
            return

        enabled = (action == "enable")
        gid = interaction.guild_id
        ensure_guild(gid)

        changed: list[str] = []
        errors: list[str] = []

        for token in [s.strip() for s in stops.split(",")]:
            if not token:
                continue

            if token == "all":
                reset_stop_overrides(gid)
                if not enabled:
                    # disable everything explicitly
                    set_stop_enabled(gid, "pre_train", False)
                    set_stop_range_enabled(gid, 1, 38, False)
                    set_stop_enabled(gid, "post_train", False)
                changed.append("all stops + pre/post")

            elif token == "all_stops":
                set_stop_range_enabled(gid, 1, 38, enabled)
                changed.append("stops 1–38")

            elif token in ("pre_train", "post_train"):
                set_stop_enabled(gid, token, enabled)
                changed.append(token)

            elif "-" in token and token.count("-") == 1:
                # Range like stop_5-stop_15
                parts = token.split("-")
                try:
                    a = int(parts[0].replace("stop_", ""))
                    b = int(parts[1].replace("stop_", ""))
                    if a > b:
                        a, b = b, a
                    set_stop_range_enabled(gid, a, b, enabled)
                    changed.append(f"stops {a}–{b}")
                except ValueError:
                    errors.append(f"`{token}` — invalid range")

            elif token.startswith("stop_"):
                try:
                    n = int(token.replace("stop_", ""))
                    if 1 <= n <= 38:
                        set_stop_enabled(gid, token, enabled)
                        changed.append(token)
                    else:
                        errors.append(f"`{token}` — stop number out of range (1–38)")
                except ValueError:
                    errors.append(f"`{token}` — not a valid stop key")
            else:
                errors.append(f"`{token}` — unrecognised")

        lines = []
        if changed:
            verb = "Enabled" if enabled else "Disabled"
            lines.append(f"{'✅' if enabled else '⏸️'} **{verb}:** {', '.join(changed)}")
        if errors:
            lines.append(f"⚠️ **Errors:** {', '.join(errors)}")
        if not lines:
            lines.append("Nothing changed.")

        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    # ------------------------------------------------------------------
    # /train_status
    # ------------------------------------------------------------------

    @app_commands.command(name="train_status", description="Show New Year Train status for this server.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def train_status(self, interaction: discord.Interaction):
        gid = interaction.guild_id
        cfg = get_guild_config(gid)
        now = datetime.now(timezone.utc)

        if not cfg:
            await interaction.response.send_message(
                "This server hasn't been set up yet. Use `/train_setup` to get started.", ephemeral=True
            )
            return

        channel = (
            f"<#{cfg['channel_id']}>" if cfg["channel_id"] else "*not set*"
        )
        state = "✅ Enabled" if cfg["enabled"] else "⏸️ Disabled"

        # Upcoming train year
        upcoming_year = now.year + 1 if now.month >= 11 else now.year
        delivered = count_delivered(gid, upcoming_year)
        total_jobs = len(get_all_jobs_for_year(upcoming_year))

        # Next pending job
        jobs = get_all_jobs_for_year(upcoming_year)
        next_info = "All done ✅"
        for j in jobs:
            if not has_delivered(gid, j["id"]):
                fire = datetime.fromisoformat(j["fire_utc"]).replace(tzinfo=timezone.utc)
                if fire > now:
                    ts = discord.utils.format_dt(fire, "R")
                    next_info = f"`{j['job_type']}` — {ts}"
                    break

        disabled = get_disabled_stops(gid)
        disabled_str = ", ".join(disabled) if disabled else "*none — all stops active*"

        embed = discord.Embed(
            title=f"🚂 New Year Train — {interaction.guild.name}",
            colour=0x00ff88 if cfg["enabled"] else 0x888888,
            timestamp=now
        )
        embed.add_field(name="Status",   value=state,   inline=True)
        embed.add_field(name="Channel",  value=channel, inline=True)
        embed.add_field(name=f"{upcoming_year} progress",
                        value=f"{delivered}/{total_jobs} jobs sent", inline=True)
        embed.add_field(name="Next job",         value=next_info,    inline=False)
        embed.add_field(name="Disabled stops",   value=disabled_str, inline=False)
        embed.set_footer(
            text="Scheduler ✅" if self.scheduler_loop.is_running() else "Scheduler ⚠️ STOPPED"
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /train_schedule  — list upcoming fire times for this guild
    # ------------------------------------------------------------------

    @app_commands.command(name="train_schedule",
                          description="List upcoming fire times for the New Year Train.")
    @app_commands.checks.has_permissions(manage_channels=True)
    async def train_schedule(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        gid = interaction.guild_id
        now = datetime.now(timezone.utc)
        upcoming_year = now.year + 1 if now.month >= 11 else now.year
        jobs = get_all_jobs_for_year(upcoming_year)

        # If every job this year is already delivered, show next year instead
        if jobs and all(has_delivered(gid, j["id"]) for j in jobs):
            upcoming_year += 1
            jobs = get_all_jobs_for_year(upcoming_year)

        lines = []
        count = 0
        for j in jobs:
            if has_delivered(gid, j["id"]):
                continue
            fire = datetime.fromisoformat(j["fire_utc"]).replace(tzinfo=timezone.utc)
            enabled_marker = "" if is_stop_enabled(gid, j["job_type"]) else " *(skipped)*"
            ts_date = discord.utils.format_dt(fire, "d")
            ts_time = discord.utils.format_dt(fire, "t")
            lines.append(f"`{j['job_type']:20}` {ts_date} {ts_time}{enabled_marker}")
            count += 1
            if count >= 20:
                lines.append(f"… and {len(jobs)-count} more")
                break

        if not lines:
            await interaction.followup.send("No pending jobs.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"🚂 {upcoming_year} Pending Schedule",
            description="\n".join(lines),
            colour=0x00aaff
        )
        embed.set_footer(text="*(skipped)* = disabled for this server")
        await interaction.followup.send(embed=embed, ephemeral=True)

    # ------------------------------------------------------------------
    # /train_preview
    # ------------------------------------------------------------------

    @app_commands.command(name="train_preview",
                          description="Preview a train message without sending it to the channel.")
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(stop="0=pre_train, 1–38=stop number, 39=post_train")
    async def train_preview(self, interaction: discord.Interaction, stop: int):
        now = datetime.now(timezone.utc)
        year = now.year + 1 if now.month >= 11 else now.year

        if stop == 0:
            msg = format_pre_train_message(year)
        elif stop == 39:
            msg = format_post_train_message(year)
        elif 1 <= stop <= 38:
            s = get_stop(stop)
            if not s:
                await interaction.response.send_message("❌ Stop not found.", ephemeral=True)
                return
            msg = format_stop_message(
                s["stop_number"], s["stop_label"], s["clock_emoji"],
                s["locations_text"], year, s["utc_offset_mins"]
            )
        else:
            await interaction.response.send_message("❌ `stop` must be 0–39.", ephemeral=True)
            return

        preview = msg[:1900] + ("…" if len(msg) > 1900 else "")
        await interaction.response.send_message(
            f"**Preview — year {year}:**\n{preview}", ephemeral=True
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TrainCog(bot))