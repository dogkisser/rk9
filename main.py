import database
import cogs
import util

import os
import asyncio
import logging
from database import WatchedTags, UserSettings, BlacklistedTags
from functools import wraps
from datetime import datetime, timezone, timedelta

import dotenv
import aiohttp
import discord
import discord.ext.commands as commands
from discord.utils import escape_markdown
from aiolimiter import AsyncLimiter

dotenv.load_dotenv()
DEBUG = os.environ.get("RK9_DEBUG") is not None
CHECK_INTERVAL = timedelta(minutes=int(os.environ.get("RK9_CHECK_INTERVAL", 15)))
DEBUG_GUILD = discord.Object(id=id) if (id := os.environ.get("RK9_DEBUG_GUILD")) else None
OWNER_ID = os.environ.get("RK9_OWNER_ID")

discord.utils.setup_logging(level=logging.DEBUG if DEBUG else logging.INFO)


def flatten(xss):
    return [x for xs in xss for x in xs]


def owner_only(func):
    @wraps(func)
    async def wrapper(i: discord.Interaction, *args, **kwargs) -> None:
        is_owner = await client.is_owner(i.user)
        if is_owner or (i.user.id == int(OWNER_ID) if OWNER_ID else False):
            return await func(i, *args, **kwargs)

        await i.response.send_message("Only my owner can use this command", ephemeral=True)

    return wrapper


class Rk9(commands.Bot):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(command_prefix="/", intents=intents)
        self.db = database.db
        # > You should make a best effort not to make more than one request per second over a
        # > sustained period.
        # - https://e621.net/help/api
        self.e6_rate_limit = AsyncLimiter(1, 1)

    async def setup_hook(self):
        await cogs.add_all(self)

        if DEBUG_GUILD:
            self.tree.copy_global_to(guild=DEBUG_GUILD)
            await self.tree.sync(guild=DEBUG_GUILD)

        watches = WatchedTags.select()
        for watch in watches:
            task_name = f"{watch.discord_id}:{watch.tags}"
            self.loop.create_task(self.check_query(watch), name=task_name)

    async def check_query(self, watch):
        await self.wait_until_ready()

        while True:
            delta_ago = datetime.now(timezone.utc) - CHECK_INTERVAL

            delay = max(0, (watch.last_check - delta_ago).total_seconds())
            await asyncio.sleep(delay)

            try:
                await self._check_query(watch)
            except Exception as e:
                logging.error("Exception in check_query. Trying again 2 minutes.\n", e)
                await asyncio.sleep(2 * 60)

    async def _check_query(self, watch):
        user = self.get_user(watch.discord_id)
        latest_posts = await self.get_latest_posts(watch)

        blacklisted_tags = set(
            [
                tag.tag
                for tag in BlacklistedTags.select().where(BlacklistedTags.discord_id == user.id)
            ]
        )

        sent = 0
        for post in latest_posts:
            flat_tags = set(flatten(post["tags"].values()))
            if not flat_tags.isdisjoint(blacklisted_tags):
                continue

            posted = datetime.fromisoformat(post["created_at"])
            if watch.last_check > posted:
                continue

            if not (channel := user.dm_channel):
                channel = await user.create_dm()

            embed = util.build_embed_from_post(post)
            embed.add_field(name="Matched query", value=f"`{watch.tags}`", inline=False)

            await channel.send(embed=embed)
            sent += 1

        watch.posts_sent += sent
        watch.last_check = datetime.now(timezone.utc)
        watch.save()

    async def get_latest_posts(self, watch):
        prefix = (
            p.prefix_tags
            if (p := UserSettings.get_or_none(UserSettings.discord_id == watch.discord_id))
            else ""
        )

        headers = {"user-agent": "github.com/dogkisser/rk9"}
        url = f"https://e621.net/posts.json?tags={watch.tags} {prefix} date:day"

        async with (
            self.e6_rate_limit,
            aiohttp.ClientSession(headers=headers) as session,
            session.get(url) as response,
        ):
            if response.status != 200:
                logging.warn(f"response != 200: {response}")

            response = await response.json()
            return response["posts"]


intents = discord.Intents.default()
intents.members = True
client = Rk9(intents=intents)


@client.event
async def on_ready():
    logging.info(f"I'm {client.user}")


@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.emoji.name == "👎":
        channel = await client.fetch_user(payload.user_id)
        message = await channel.fetch_message(payload.message_id)

        if any("👎" in e.footer.text for e in message.embeds):
            await message.delete()


@client.tree.command()
async def info(interaction: discord.Interaction):
    """List your prefix and information about your followed queries"""
    uid = interaction.user.id

    queries = WatchedTags.select(
        WatchedTags.tags, WatchedTags.posts_sent, WatchedTags.last_check
    ).where(WatchedTags.discord_id == interaction.user.id)
    settings = UserSettings.get_or_none(UserSettings.discord_id == uid)
    blacklisted = [t.tag for t in BlacklistedTags.select().where(BlacklistedTags.discord_id == uid)]

    total_posts_sent = sum(q.posts_sent for q in queries)
    total_tags = sum(len(q.tags.split()) for q in queries)
    total_queries = len(queries)

    paginator = commands.Paginator(prefix="", suffix="")
    for query in queries:
        next_check = int((query.last_check + CHECK_INTERVAL).timestamp())

        paginator.add_line(
            f"### `{query.tags}`\n* Posts sent: {query.posts_sent}\n"
            + f"* Next check: <t:{next_check}:R>\n"
        )

    await interaction.response.send_message(
        f"* Prefix: {f'`{settings.prefix_tags}`' if settings else settings}\n"
        + f"* Total posts sent: {total_posts_sent}\n"
        + f"* Total tags watched: {total_tags}\n"
        + f"* Total queries watched: {total_queries}\n"
        + f"* Subscribed to popular: {settings.subscribed_to_popular if settings else 'False'}\n"
        + f"* Blacklisted: {f'||`{" ".join(blacklisted)}`||' if blacklisted else 'None'}",
        ephemeral=True,
    )

    for page in paginator.pages:
        await interaction.followup.send(page, ephemeral=True)


@client.tree.command()
@owner_only
async def sync(interaction: discord.Interaction):
    """Sync commands globally"""
    await client.tree.sync()
    await interaction.response.send_message("Syncing", ephemeral=True)


client.run(os.environ["RK9_DISCORD_TOKEN"])
