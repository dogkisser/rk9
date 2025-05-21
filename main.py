import database
from database import WatchedTags

import os
import traceback
import string
import asyncio
from datetime import *

import peewee
import dotenv
import aiohttp
import discord
import discord.ext.commands
from discord import app_commands
from discord.utils import escape_markdown

dotenv.load_dotenv()

MY_GUILD = discord.Object(id=os.environ['RK9_DEBUG_GUILD'])
CHECK_INTERVAL = timedelta(minutes=15)

class TagError(ValueError):
    pass

def normalise_tags(tags: str | list[str]) -> str:
    """Normalises a tag string or list of tags into a tag string"""

    if isinstance(tags, str):
        tags = tags.split()
    tag_list = list(set(map(str.lower, tags)))
    tag_list.sort()
    # Managed by the bot
    tag_list = [tag for tag in tag_list if not tag.startswith(('order:', 'date:'))]

    # https://e621.net/help/tags
    # "Tags may only contain English letters, numbers, and some symbols."
    for tag in tag_list:
        if not all(c in string.printable for c in tag):
            raise TagError('tags contain characters disallowed by e621')

    return ' '.join(tag_list)

class AddWatchModal(discord.ui.Modal, title='Watch'):
    tags = discord.ui.TextInput(
        label='Tags',
        placeholder='loona_(helluva_boss) solo',
        style=discord.TextStyle.long,
    )

    async def on_submit(self, interaction: discord.Interaction):
        try:
            normalised_tags = normalise_tags(self.tags.value)
        except TagError as e:
            await interaction.response.send_message(e, ephemeral=True)
            return

        watched = WatchedTags(
            discord_id=interaction.user.id,
            tags=normalised_tags,
        )

        try:
            watched.save()
            await interaction.response.send_message('Added', ephemeral=True)
        except peewee.IntegrityError:
            await interaction.response.send_message('You\'re already watching an identical query',
                ephemeral=True)
    
    async def on_error(self, interaction: discord.Interaction, error: Exception):
        await interaction.response.send_message(f'Internal error.', ephemeral=True)

        traceback.print_exception(type(error), error, error.__traceback__)

class UnfollowDropdown(discord.ui.Select):
    def __init__(self, queries, **kwargs):
        options = [discord.SelectOption(label=query) for query in queries]
        super().__init__(placeholder='Select query', **kwargs, max_values=len(options), options=options)

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

    @discord.ui.button(label='Unfollow', row=1, style=discord.ButtonStyle.red)
    async def unfollow(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()

        query = WatchedTags.delete().where(
            (WatchedTags.discord_id == interaction.user.id) &
            (WatchedTags.tags << self.unfollow_dropdown.values)
        )
        query.execute()

        await interaction.response.edit_message(content='Done', view=None)

class Rk9(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)

        self.db = database.db
        self.db.connect()
        self.db.create_tables([WatchedTags])

        # Used to limit the number of concurrent requests to the e621 API.
        # e6's rate limit strictly is two requests per second, this is a bit of a hack that should
        # roughly work. May require fiddling.
        self.e6_api_semaphore = asyncio.Semaphore(2)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

        watches = WatchedTags.select()
        for watch in watches:
            self.loop.create_task(self.check_query(watch))

    async def check_query(self, watch):
        while True:
            delta_ago = datetime.now() - CHECK_INTERVAL
            if not (last_check := watch.last_check):
                last_check = datetime.now()
                watch.last_check = last_check
                watch.save()

            delay = max(0, (last_check - delta_ago).total_seconds())

            user = await self.fetch_user(watch.discord_id)

            # await asyncio.sleep(delay)

            latest_posts = await self.get_latest_posts(watch)
            for post in latest_posts['posts']:
                # convert to UTC then remove the timezone information.
                posted_tz = datetime.fromisoformat(post['created_at'])
                posted = posted_tz.astimezone(
                    timezone.utc).replace(tzinfo=None)

                if posted < last_check:
                    continue

                author = ', '.join(post['tags']['artist'])

                if not (channel := user.dm_channel):
                    channel = await user.create_dm()

                embed = discord.Embed(title=f'#{post['id']}',
                    url=f'https://e621.net/posts/{post['id']}',
                    description=post['description'][:50] + (post['description'][50:] and '..'),
                    colour=0x1f2f56,
                    timestamp=posted_tz)
                embed.add_field(name="Matched query",
                    value=watch.tags,
                    inline=False)
                embed.set_image(url=post['file']['url'])
                embed.set_footer(text="/rk9/")

                if author:
                    embed.set_author(name=author)

                await channel.send(embed=embed)

            watch.last_check = datetime.now()
            watch.save()

            await asyncio.sleep(delay)

    async def get_latest_posts(self, watch):
        headers = {'user-agent': 'github.com/dogkisser/rk9'}
        url = f'https://e621.net/posts.json?tags={watch.tags} date:day'

        async with self.e6_api_semaphore:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as response:
                    response = await response.json()
                    return response

intents = discord.Intents.default()
client = Rk9(intents=intents)

@client.event
async def on_ready():
    print(f'I\'m {client.user}')

@client.tree.command()
async def follow(interaction: discord.Interaction):
    """Follow a new query"""
    await interaction.response.send_modal(AddWatchModal())

@client.tree.command()
async def unfollow(interaction: discord.Interaction):
    """Stop following a query/queries"""
    queries = WatchedTags.select(WatchedTags.tags).where(
        WatchedTags.discord_id == interaction.user.id)
    queries = [q.tags for q in queries]

    view = UnfollowView(queries)
    await interaction.response.send_message(ephemeral=True, view=view)

@client.tree.command()
async def following(interaction: discord.Interaction):
    """Lists the queries you're following and when they'll be next checked"""
    queries = WatchedTags.select(WatchedTags.tags, WatchedTags.last_check).where(
        WatchedTags.discord_id == interaction.user.id
    )

    if not queries:
        await interaction.response.send_message('You\'re not following any queries.')
        return

    fmt = []
    for query in queries:
        last_check = query.last_check if query.last_check else datetime.now()
        next_check = (last_check + timedelta(minutes=30)).timestamp()
        fmt.append(f'* `{query.tags}` next check: <t:{int(next_check)}:R>') 
    fmt = '\n'.join(fmt)

    await interaction.response.send_message(fmt)

client.run(os.environ['RK9_DISCORD_TOKEN'])