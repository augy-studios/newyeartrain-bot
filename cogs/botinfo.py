"""
cogs/botinfo.py — /botinfo command showing system and bot statistics.
"""

import discord
from discord.ext import commands
from discord import app_commands
import platform
import socket
import sys
import os
import psutil
from datetime import datetime, timezone, timedelta

log = __import__("logging").getLogger("new_year_train.botinfo")


def _fmt_uptime(seconds: float) -> str:
    td = timedelta(seconds=int(seconds))
    h, remainder = divmod(td.seconds, 3600)
    m, s = divmod(remainder, 60)
    days = td.days
    if days:
        return f"{days}d {h:02}:{m:02}:{s:02}"
    return f"{h:02}:{m:02}:{s:02}"


def _fmt_bytes(b: float) -> str:
    if b >= 1 << 30:
        return f"{b / (1 << 30):.2f}GB"
    return f"{b / (1 << 20):.2f}MB"


class BotInfoCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="botinfo", description="Show system and bot information.")
    async def botinfo(self, interaction: discord.Interaction):
        proc = psutil.Process(os.getpid())

        os_name = f"{platform.system()} {platform.release()}"
        uptime = _fmt_uptime(datetime.now(timezone.utc).timestamp() - proc.create_time())
        hostname = socket.gethostname()
        arch = platform.machine()
        cores = os.cpu_count() or 1
        cpu_pct = psutil.cpu_percent(interval=0.1)

        vm = psutil.virtual_memory()
        mem_used = _fmt_bytes(vm.used)
        mem_total = _fmt_bytes(vm.total)

        py_version = f"v{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        dpy_version = discord.__version__

        guilds = self.bot.guilds
        guild_count = len(guilds)
        channel_count = sum(len(g.channels) for g in guilds)
        member_count = sum(g.member_count or 0 for g in guilds)

        cmds = self.bot.tree.get_commands()
        total_cmds = len(cmds)

        embed = discord.Embed(title="Bot Information", colour=0x57F287)
        embed.add_field(name="Operating System",   value=os_name,                                          inline=False)
        embed.add_field(name="Uptime",             value=uptime,                                           inline=False)
        embed.add_field(name="Hostname",           value=hostname,                                         inline=False)
        embed.add_field(name="CPU Architecture",   value=f"{arch} ({cores} cores)",                        inline=False)
        embed.add_field(name="CPU Usage",          value=f"{cpu_pct}%",                                    inline=False)
        embed.add_field(name="Memory Usage",       value=f"{mem_used} / {mem_total}",                      inline=False)
        embed.add_field(name="Python Version",     value=py_version,                                       inline=False)
        embed.add_field(name="discord.py Version", value=dpy_version,                                      inline=False)
        embed.add_field(name="Connected to",       value=f"{guild_count} guilds, {channel_count} channels, and {member_count} users", inline=False)
        embed.add_field(name="Total Commands",     value=str(total_cmds),                                  inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=False)
        log.info(f"[guild={interaction.guild_id}] /botinfo used by {interaction.user}")


async def setup(bot: commands.Bot):
    await bot.add_cog(BotInfoCog(bot))
