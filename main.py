import database
from database import WatchedTags

import os
import string
import asyncio
import logging
from datetime import *

import peewee
import dotenv
import aiohttp
import discord
from discord.utils import escape_markdown

dotenv.load_dotenv()
DEBUG = os.environ.get('RK9_DEBUG') is not None

discord.utils.setup_logging(level=logging.DEBUG if DEBUG else logging.INFO)

MY_GUILD = discord.Object(id=os.environ['RK9_DEBUG_GUILD'])
CHECK_INTERVAL = timedelta(minutes=2 if DEBUG else 15)

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

        for tags in self.unfollow_dropdown.values:
            task_name = f'{interaction.user.id}:{tags}'
            [task.cancel() for task in asyncio.all_tasks() if task.get_name() == task_name]

        await interaction.response.edit_message(content='Done', view=None)

class Rk9(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

        self.db = database.db
        self.db.connect()
        self.db.create_tables([WatchedTags])

        # Used to limit the number of concurrent requests to the e621 API.
        # e6's rate limit strictly is two requests per second, this is a bit of a hack that should
        # roughly work. May require fiddling.
        # possible idea: sleep at the end of the api request while still holding the semaphore for
        # ~500ms
        self.e6_api_semaphore = asyncio.Semaphore(2)

    async def setup_hook(self):
        self.tree.copy_global_to(guild=MY_GUILD)
        await self.tree.sync(guild=MY_GUILD)

        watches = WatchedTags.select()
        for watch in watches:
            task_name = f'{watch.discord_id}:{watch.tags}'
            self.loop.create_task(self.check_query(watch), name=task_name)

    async def check_query(self, watch):
        while True:
            delta_ago = datetime.now(timezone.utc) - CHECK_INTERVAL
            last_check = watch.last_check.replace(tzinfo=timezone.utc)

            delay = max(0, (last_check - delta_ago).total_seconds())
            await asyncio.sleep(delay)

            logging.info(f'Running check for {watch.discord_id}:{watch.tags}')
            await self._check_query(watch)
        
    async def _check_query(self, watch):
            user = await self.fetch_user(watch.discord_id)
            last_check = watch.last_check.replace(tzinfo=timezone.utc)

            latest_posts = await self.get_latest_posts(watch)
            logging.debug(f'{watch.tags} yields {len(latest_posts)}')
            for post in latest_posts['posts']:
                posted = datetime.fromisoformat(post['created_at'])

                if last_check > posted:
                    logging.debug(f'lc>p {last_check} > {posted}')
                    continue

                author = ', '.join(post['tags']['artist'])

                if not (channel := user.dm_channel):
                    channel = await user.create_dm()

                logging.debug(f'Sending {post}')
                # post['file']['url'] is null if the post is on the global blacklist, but all the
                # other information is intact. we reconstruct the url ourself to side-step.
                img_hash = post['file']['md5']
                url = f'https://static1.e621.net/data/{img_hash[0:2]}/{img_hash[2:4]}/{img_hash}.{post['file']['ext']}'
                description = post['description'][:50] + (post['description'][50:] and '..')
                embed = discord.Embed(title=f'#{post['id']}',
                    url=f'https://e621.net/posts/{post['id']}',
                    description=escape_markdown(description),
                    colour=0x1f2f56,
                    timestamp=posted)
                embed.add_field(name="Matched query",
                    value=f'`{watch.tags}`',
                    inline=False)
                embed.set_image(url=url)
                embed.set_footer(text="/rk9/ • 👎 to remove")

                if author:
                    embed.set_author(name=author)

                await channel.send(embed=embed)

            watch.last_check = datetime.now(timezone.utc).replace(tzinfo=None)
            watch.save()

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
    logging.info(f'I\'m {client.user}')

@client.tree.command()
async def follow(interaction: discord.Interaction, query: str):
    """Follow a new query"""
    try:
        normalised_query = normalise_tags(query)

        watched = WatchedTags(
            discord_id=interaction.user.id,
            tags=normalised_query,
            last_check=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        watched.save()

        task_name = f'{watched.discord_id}:{watched.tags}'
        client.loop.create_task(client.check_query(watched), name=task_name)

        await interaction.response.send_message('Added', ephemeral=True)
    except TagError as e:
        await interaction.response.send_message(e, ephemeral=True)
    except peewee.IntegrityError:
        await interaction.response.send_message('You\'re already watching an identical query',
            ephemeral=True)

@client.tree.command()
async def unfollow(interaction: discord.Interaction):
    """Stop following a query/queries"""
    queries = WatchedTags.select(WatchedTags.tags).where(
        WatchedTags.discord_id == interaction.user.id)
    queries = [q.tags for q in queries]

    if not queries:
        await interaction.response.send_message('You\'re not following any queries', ephemeral=True)
        return

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
        last_check = query.last_check.replace(tzinfo=timezone.utc)
        next_check = (last_check + CHECK_INTERVAL).timestamp()
        fmt.append(f'* `{query.tags}` next check est. <t:{int(next_check)}:R>') 
    fmt = '\n'.join(fmt)

    await interaction.response.send_message(fmt)

@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.emoji.name == '👎':
        channel = await client.fetch_user(payload.user_id)
        message = await channel.fetch_message(payload.message_id)

        await message.delete()

# TODO: Admin only!!
@client.tree.command()
async def sync(interaction: discord.Interaction):
    """Sync commands globally"""
    await client.tree.sync()
    await interaction.response.send_message('Syncing')

client.run(os.environ['RK9_DISCORD_TOKEN'])