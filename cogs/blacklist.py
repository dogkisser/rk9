from database import BlacklistedTags

import discord
import discord.ext.commands as commands
from discord import app_commands


class Blacklist(commands.GroupCog, name="blacklist"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command(name="add")
    async def blacklist_add(self, interaction: discord.Interaction, tags: str) -> None:
        """
        Add tags to your blacklist

        Args:
            tags: One or more tags to add to your blacklist.
        """
        data = [{"discord_id": interaction.user.id, "tag": tag} for tag in tags.split(" ")]
        BlacklistedTags.insert_many(data).on_conflict_ignore().execute()

        await interaction.response.send_message("Done", ephemeral=True)

    @app_commands.command(name="remove")
    async def blacklist_remove(self, interaction: discord.Interaction, tags: str) -> None:
        """
        Remove tags from your blacklist

        Args:
            tags: One or more tags to remove from your blacklist.
        """
        tag_list = tags.split(" ")

        BlacklistedTags.delete().where(
            BlacklistedTags.discord_id == interaction.user.id, BlacklistedTags.tag << tag_list
        ).execute()

        await interaction.response.send_message("Done", ephemeral=True)
