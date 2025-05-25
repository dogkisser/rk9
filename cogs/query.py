from database import WatchedTags
from util import normalise_tags, TagError

from datetime import datetime, timezone
import asyncio

import peewee
import discord
import discord.ext.commands as commands
from discord import app_commands


class UnfollowDropdown(discord.ui.Select):
    def __init__(self, queries, **kwargs):
        options = [
            discord.SelectOption(label=query[:98] + (query[98:] and ".."), value=str(i))
            for (i, query) in enumerate(queries)
        ]
        super().__init__(
            placeholder="Select query", **kwargs, max_values=len(options), options=options
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.defer(thinking=False)


# Maximum of 25 queries per invocation
class UnfollowView(discord.ui.View):
    def __init__(self, queries):
        self.queries = queries
        self.selected = []

        super().__init__()

        self.unfollow_dropdown = UnfollowDropdown(self.queries, row=0)
        self.add_item(self.unfollow_dropdown)

    @discord.ui.button(label="Unfollow", row=1, style=discord.ButtonStyle.red)
    async def unfollow(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()

        delete = [self.queries[int(i)] for i in self.unfollow_dropdown.values]
        query = WatchedTags.delete().where(
            (WatchedTags.discord_id == interaction.user.id) & (WatchedTags.tags << delete)
        )
        query.execute()

        for tags in delete:
            task_name = f"{interaction.user.id}:{tags}"
            [task.cancel() for task in asyncio.all_tasks() if task.get_name() == task_name]

        await interaction.response.edit_message(content="Done", view=None)


class Query(commands.GroupCog, name="query"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @app_commands.command()
    async def follow(self, interaction: discord.Interaction, query: str) -> None:
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
    async def unfollow(self, interaction: discord.Interaction) -> None:
        """Stop following a query/queries"""
        queries = WatchedTags.select(WatchedTags.tags).where(
            WatchedTags.discord_id == interaction.user.id
        )
        queries = [q.tags for q in queries]

        if not queries:
            await interaction.response.send_message(
                "You're not following any queries", ephemeral=True
            )
            return

        view = UnfollowView(queries)
        await interaction.response.send_message(ephemeral=True, view=view)
