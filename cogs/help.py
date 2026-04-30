"""
cogs/help.py — Paginated /help command.
"""

import discord
from discord.ext import commands
from discord import app_commands

PAGES = [
    discord.Embed(
        title="🚂 New Year Train — Help (1/3)",
        description="All commands require the **Manage Channels** permission.",
        colour=0x00aaff,
    ).add_field(name="/train_setup [channel]", value="Enable the bot and set the posting channel.", inline=False)
     .add_field(name="/train_toggle [enabled]", value="Pause or resume the whole train.", inline=False)
     .add_field(name="/train_setchannel [channel]", value="Change the posting channel.", inline=False)
     .add_field(name="/train_stops [action] [stops]", value="Enable or disable specific stops or ranges.\nTokens: `all`, `all_stops`, `stop_11`, `stop_5-stop_15`, `pre_train`, `post_train`", inline=False),

    discord.Embed(
        title="🚂 New Year Train — Help (2/3)",
        colour=0x00aaff,
    ).add_field(name="/train_status", value="Show current config and delivery progress.", inline=False)
     .add_field(name="/train_schedule", value="List upcoming fire times.", inline=False)
     .add_field(name="/train_preview [stop]", value="Preview a message without sending it.\n`0` = pre-train, `1–38` = stop, `39` = post-train.", inline=False)
     .add_field(name="/train_rebuild [year]", value="Force-rebuild the global schedule for a year.", inline=False),

    discord.Embed(
        title="🚂 New Year Train — Help (3/3)",
        colour=0x00aaff,
    ).add_field(name="/train_reset [year]", value="Clear the delivery log for this server (useful for testing).", inline=False)
     .add_field(name="/train_sendnow [year] [job_type]", value="Immediately send a job to this server's channel.\ne.g. `pre_train`, `stop_11`, `post_train`.", inline=False)
     .add_field(name="/train_dbinfo", value="Show database statistics.", inline=False)
     .add_field(name="/train_guilds", value="List all registered servers.", inline=False),
]


class HelpView(discord.ui.View):
    def __init__(self, page: int = 0):
        super().__init__(timeout=120)
        self.page = page
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.page == 0
        self.next_button.disabled = self.page == len(PAGES) - 1

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page -= 1
        self._update_buttons()
        await interaction.response.edit_message(embed=PAGES[self.page], view=self)

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page += 1
        self._update_buttons()
        await interaction.response.edit_message(embed=PAGES[self.page], view=self)

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="List all New Year Train commands.")
    async def help(self, interaction: discord.Interaction):
        view = HelpView(page=0)
        await interaction.response.send_message(embed=PAGES[0], view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(HelpCog(bot))
