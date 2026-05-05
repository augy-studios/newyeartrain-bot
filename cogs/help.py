"""
cogs/help.py — Paginated /help command.
"""

import discord
from discord.ext import commands
from discord import app_commands


def _mention(name: str, cmd_ids: dict) -> str:
    cid = cmd_ids.get(name)
    return f"</{name}:{cid}>" if cid else f"/{name}"


def _make_pages(cmd_ids: dict) -> list:
    m = lambda n: _mention(n, cmd_ids)
    return [
        discord.Embed(
            title="🚂 New Year Train — Help (1/3)",
            description="All commands require the **Manage Channels** permission.",
            colour=0x00aaff,
        ).add_field(name=f"{m('setup')} [channel]", value="Enable the bot and set the posting channel.", inline=False)
         .add_field(name=f"{m('toggle')} [enabled]", value="Pause or resume the whole train.", inline=False)
         .add_field(name=f"{m('setchannel')} [channel]", value="Change the posting channel.", inline=False)
         .add_field(name=f"{m('stops')} [action] [stops]", value="Enable or disable specific stops or ranges.\nTokens: `all`, `all_stops`, `stop_11`, `stop_5-stop_15`, `pre_train`, `post_train`", inline=False),

        discord.Embed(
            title="🚂 New Year Train — Help (2/3)",
            colour=0x00aaff,
        ).add_field(name=m('status'), value="Show current config and delivery progress.", inline=False)
         .add_field(name=m('schedule'), value="List upcoming fire times.", inline=False)
         .add_field(name=f"{m('preview')} [stop]", value="Preview a message without sending it.\n`0` = pre-train, `1–38` = stop, `39` = post-train.", inline=False)
         .add_field(name=f"{m('rebuild')} [year]", value="Force-rebuild the global schedule for a year.", inline=False),

        discord.Embed(
            title="🚂 New Year Train — Help (3/3)",
            colour=0x00aaff,
        ).add_field(name=f"{m('reset')} [year]", value="Clear the delivery log for this server (useful for testing).", inline=False)
         .add_field(name=f"{m('sendnow')} [year] [job_type]", value="Immediately send a job to this server's channel.\ne.g. `pre_train`, `stop_11`, `post_train`.", inline=False)
         .add_field(name=m('dbinfo'), value="Show database statistics.", inline=False)
         .add_field(name=m('guilds'), value="List all registered servers.", inline=False),
    ]


class HelpView(discord.ui.View):
    def __init__(self, pages: list, page: int = 0):
        super().__init__(timeout=120)
        self.pages = pages
        self.page = page
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page == len(self.pages) - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=self.pages[self.page], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="List all New Year Train commands.")
    async def help(self, interaction: discord.Interaction):
        cmd_ids = getattr(interaction.client, "command_ids", {})
        pages = _make_pages(cmd_ids)
        view = HelpView(pages=pages, page=0)
        await interaction.response.send_message(embed=pages[0], view=view, ephemeral=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
