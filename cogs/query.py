from database import WatchedTags
from util import normalise_tags, TagError

from datetime import datetime, timezone

import peewee
import discord
import discord.ext.commands as commands
from discord import app_commands


class Query(commands.GroupCog, name="query"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command()
    async def add(self, interaction: discord.Interaction, query: str) -> None:
        """Follow a new query"""
        try:
            normalised_query = normalise_tags(query)

            watched = WatchedTags(
                discord_id=interaction.user.id,
                tags=normalised_query,
                last_check=datetime.now(timezone.utc),
            )
            watched.save()

            task_name = f"{watched.discord_id}:{watched.tags}"
            self.bot.loop.create_task(self.bot.check_query(watched), name=task_name)

            await interaction.response.send_message("Added", ephemeral=True)
        except TagError as e:
            await interaction.response.send_message(e, ephemeral=True)
        except peewee.IntegrityError:
            await interaction.response.send_message(
                "You're already watching an identical query", ephemeral=True
            )

    @app_commands.command()
    async def remove(self, interaction: discord.Interaction, query: str) -> None:
        """Stop following a query"""
        existed = (
            WatchedTags.delete()
            .where(WatchedTags.discord_id == interaction.user.id, WatchedTags.tags == query)
            .execute()
            > 0
        )
        message = "Deleted" if existed else "No such query exists"

        await interaction.response.send_message(message, ephemeral=True)

    @app_commands.command()
    async def find(self, interaction: discord.Interaction, containing: str) -> None:
        """Check whether a query containing certain tags exists"""
        target = containing.split()
        queries = WatchedTags.select(WatchedTags.tags).where(
            WatchedTags.discord_id == interaction.user.id
        )

        results = ""
        for query in queries:
            if all(tag in query.tags for tag in target):
                results += f"- `{query.tags}`\n"

        if not results:
            results = "No results"

        await interaction.response.send_message(results, ephemeral=True)
