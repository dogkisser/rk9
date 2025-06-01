from database import WatchedTags

from datetime import datetime, timezone
from typing import Literal

import peewee
import discord
import discord.ext.commands as commands
from discord import app_commands


class Query(commands.GroupCog, name="query"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command()
    async def add(
        self, interaction: discord.Interaction, query: str, mode: Literal["raw", "separate"] = "raw"
    ) -> None:
        """
        Follow a new query

        Args:
            query: The tag or list of tags to add to your list of queries
            mode: raw (default): add as a single query; separate: add add multiple individual tag
                queries
        """
        queries = [query] if mode == "raw" else query.split()
        for query in queries:
            try:
                watched = WatchedTags(
                    discord_id=interaction.user.id,
                    tags=query,
                    last_check=datetime.now(timezone.utc),
                )
                watched.save()

                task_name = f"{watched.discord_id}:{watched.tags}"
                self.bot.loop.create_task(self.bot.check_query(watched), name=task_name)
            except peewee.IntegrityError:
                # UNIQUE(discord_id, last_check)
                # just ignore it
                continue

        await interaction.response.send_message("Done", ephemeral=True)

    @app_commands.command()
    async def remove(self, interaction: discord.Interaction, query: str) -> None:
        """
        Stop following a query

        Args:
            query: The query to unfollow
        """
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
