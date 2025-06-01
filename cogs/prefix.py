from database import db, UserSettings

import discord
import discord.ext.commands as commands
from discord import app_commands


class Prefix(commands.GroupCog, name="prefix"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="set")
    async def prefix_set(self, interaction: discord.Interaction, query: str):
        """
        Update your tag prefix

        Args:
            query: Your updated prefix
        """
        with db.atomic():
            i, _ = UserSettings.get_or_create(discord_id=interaction.user.id)
            i.prefix_tags = query
            i.save()

        await interaction.response.send_message("Prefix updated", ephemeral=True)

    @app_commands.command(name="clear")
    async def prefix_clear(self, interaction: discord.Interaction):
        """Clear your tag prefix"""
        with db.atomic():
            i, _ = UserSettings.get_or_create(discord_id=interaction.user.id)
            i.prefix_tags = ""
            i.save()

        await interaction.response.send_message("Prefix updated", ephemeral=True)
