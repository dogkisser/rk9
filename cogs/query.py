from math import ceil
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
        self.page = 0
        self.last_page = ceil(len(self.queries) / 25) - 1

        super().__init__()

        self.unfollow_dropdown = UnfollowDropdown(self.queries[:25], row=0)
        self.add_item(self.unfollow_dropdown)

        self.children[2].disabled = self.page == self.last_page

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

    @discord.ui.button(label="⬅️", disabled=True, row=1, style=discord.ButtonStyle.gray)
    async def page_left(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = max(0, self.page - 1)
        await self.update_dropdown(interaction)

    @discord.ui.button(label="➡️", row=1, style=discord.ButtonStyle.gray)
    async def page_right(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.page = min(self.last_page, self.page + 1)
        await self.update_dropdown(interaction)

    async def update_dropdown(self, interaction: discord.Interaction):
        start = self.page * 25
        new = self.queries[start : start + 25]

        self.remove_item(self.unfollow_dropdown)
        self.unfollow_dropdown = UnfollowDropdown(new, row=0)
        self.children.insert(0, self.unfollow_dropdown)
        self.add_item(self.unfollow_dropdown)

        self.children[1].disabled = self.page == 0
        self.children[2].disabled = self.page == self.last_page

        await interaction.response.edit_message(view=self)


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
    async def remove(self, interaction: discord.Interaction) -> None:
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
