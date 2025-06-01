from database import PrefixTags

import discord
import discord.ext.commands as commands
from discord import app_commands


class Prefix(commands.GroupCog, name="prefix"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="set")
    async def prefix_set(self, interaction: discord.Interaction, query: str):
        """Update your tag prefix"""
        PrefixTags.replace(discord_id=interaction.user.id, tags=query).execute()

        await interaction.response.send_message("Prefix updated", ephemeral=True)

    @app_commands.command(name="clear")
    async def prefix_clear(self, interaction: discord.Interaction):
        """Clear your tag prefix"""
        PrefixTags.delete().where(PrefixTags.discord_id == interaction.user.id).execute()

        await interaction.response.send_message("Prefix updated", ephemeral=True)
