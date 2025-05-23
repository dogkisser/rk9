import database
from database import WatchedTags, PrefixTags

import os
import string
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import peewee
import dotenv
import aiohttp
import discord
from discord.utils import escape_markdown

dotenv.load_dotenv()
DEBUG = os.environ.get("RK9_DEBUG") is not None
CHECK_INTERVAL = timedelta(minutes=int(os.environ.get("RK9_CHECK_INTERVAL", 15)))
DEBUG_GUILD = discord.Object(id=id) if (id := os.environ.get("RK9_DEBUG_GUILD")) else None

discord.utils.setup_logging(level=logging.DEBUG if DEBUG else logging.INFO)


class TagError(ValueError):
    pass


def normalise_tags(tags: str) -> str:
    if not all(c in string.printable for c in tags):
        raise TagError("tags contain characters disallowed by e621")

    if len(tags.split()) > 40:
        raise TagError("too many tags in query (> 40)")

    return tags.lower()


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


class Rk9(discord.Client):
    def __init__(self, *, intents: discord.Intents):
        super().__init__(intents=intents)
        self.tree = discord.app_commands.CommandTree(self)

        self.db = database.db
        self.db.connect()
        self.db.create_tables([WatchedTags, PrefixTags])

        # Used to limit the number of concurrent requests to the e621 API.
        # e6's rate limit strictly is two requests per second, this is a bit of a hack that should
        # roughly work. May require fiddling.
        # possible idea: sleep at the end of the api request while still holding the semaphore for
        # ~500ms
        self.e6_api_semaphore = asyncio.Semaphore(2)

    async def setup_hook(self):
        if DEBUG_GUILD:
            self.tree.copy_global_to(guild=DEBUG_GUILD)
            await self.tree.sync(guild=DEBUG_GUILD)

        watches = WatchedTags.select()
        for watch in watches:
            task_name = f"{watch.discord_id}:{watch.tags}"
            self.loop.create_task(self.check_query(watch), name=task_name)

    async def check_query(self, watch):
        while True:
            delta_ago = datetime.now(timezone.utc) - CHECK_INTERVAL
            last_check = watch.last_check.replace(tzinfo=timezone.utc)

            delay = max(0, (last_check - delta_ago).total_seconds())
            await asyncio.sleep(delay)

            logging.info(f"Running check for {watch.discord_id}:{watch.tags}")
            await self._check_query(watch)

    async def _check_query(self, watch):
        user = await self.fetch_user(watch.discord_id)
        last_check = watch.last_check.replace(tzinfo=timezone.utc)

        latest_posts = await self.get_latest_posts(watch)
        logging.debug(f"{watch.tags} yields {len(latest_posts)}")
        for post in latest_posts:
            posted = datetime.fromisoformat(post["created_at"])

            if last_check > posted:
                continue

            author = ", ".join(post["tags"]["artist"])

            if not (channel := user.dm_channel):
                channel = await user.create_dm()

            logging.debug(f"Sending {post}")
            # post['file']['url'] is null if the post is on the global blacklist, but all the
            # other information is intact. we reconstruct the url ourself to side-step.
            img_hash = post["file"]["md5"]
            # try to use the sample if it exists, discord can't embed videos
            data_seg = "/data/sample/" if post["sample"]["has"] else "/data/"
            ext = "jpg" if post["sample"]["has"] else post["file"]["ext"]
            url = f"https://static1.e621.net{data_seg}{img_hash[0:2]}/{img_hash[2:4]}/{img_hash}.{ext}"
            description = post["description"][:150] + (post["description"][150:] and "..")
            embed = discord.Embed(
                title=f"#{post['id']}",
                url=f"https://e621.net/posts/{post['id']}",
                description=escape_markdown(description),
                colour=0x1F2F56,
                timestamp=posted,
            )
            embed.add_field(name="Matched query", value=f"`{watch.tags}`", inline=False)
            embed.set_image(url=url)
            embed.set_footer(text="/rk9/ • 👎 to remove")

            if post["file"]["ext"] in ["webm", "mp4"]:
                embed.add_field(name=":play_pause: Animated", value="", inline=False)

            if author:
                embed.set_author(name=author)

            await channel.send(embed=embed)

        watch.last_check = datetime.now(timezone.utc).replace(tzinfo=None)
        watch.save()

    async def get_latest_posts(self, watch):
        prefix = (
            p.tags
            if (p := PrefixTags.get_or_none(PrefixTags.discord_id == watch.discord_id))
            else ""
        )

        headers = {"user-agent": "github.com/dogkisser/rk9"}
        url = f"https://e621.net/posts.json?tags={watch.tags} {prefix} date:day"

        async with (
            self.e6_api_semaphore,
            aiohttp.ClientSession(headers=headers) as session,
            session.get(url) as response,
        ):
            if response.status != 200:
                logging.warn(f"response != 200: {response}")

            response = await response.json()
            return response["posts"]


intents = discord.Intents.default()
client = Rk9(intents=intents)


@client.event
async def on_ready():
    logging.info(f"I'm {client.user}")


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

        task_name = f"{watched.discord_id}:{watched.tags}"
        client.loop.create_task(client.check_query(watched), name=task_name)

        await interaction.response.send_message("Added", ephemeral=True)
    except TagError as e:
        await interaction.response.send_message(e, ephemeral=True)
    except peewee.IntegrityError:
        await interaction.response.send_message(
            "You're already watching an identical query", ephemeral=True
        )


@client.tree.command()
async def unfollow(interaction: discord.Interaction):
    """Stop following a query/queries"""
    queries = WatchedTags.select(WatchedTags.tags).where(
        WatchedTags.discord_id == interaction.user.id
    )
    queries = [q.tags for q in queries]

    if not queries:
        await interaction.response.send_message("You're not following any queries", ephemeral=True)
        return

    view = UnfollowView(queries)
    await interaction.response.send_message(ephemeral=True, view=view)


@client.tree.command()
async def info(interaction: discord.Interaction):
    """List your prefix, followed queries, and when they'll be checked next"""
    uid = interaction.user.id

    queries = WatchedTags.select(WatchedTags.tags, WatchedTags.last_check).where(
        WatchedTags.discord_id == interaction.user.id
    )

    result = (
        f"Prefix: `{p.tags}`\n"
        if (p := PrefixTags.get_or_none(PrefixTags.discord_id == uid))
        else "No prefix set.\n"
    )

    if queries:
        fmt = []
        for query in queries:
            last_check = query.last_check.replace(tzinfo=timezone.utc)
            next_check = (last_check + CHECK_INTERVAL).timestamp()
            fmt.append(f"* `{query.tags}` next check est. <t:{int(next_check)}:R>")
        result += "\n".join(fmt)

    if not result:
        result = "You're not following any queries."

    await interaction.response.send_message(result, ephemeral=True)


@client.tree.command()
async def prefix(interaction: discord.Interaction, query: str):
    """Set a list of tags applied to all queries automatically"""
    PrefixTags.replace(discord_id=interaction.user.id, tags=normalise_tags(query)).execute()

    await interaction.response.send_message("Prefix updated", ephemeral=True)


# TODO: probably should check if the reacted message is an image or just a random message
@client.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.emoji.name == "👎":
        channel = await client.fetch_user(payload.user_id)
        message = await channel.fetch_message(payload.message_id)

        await message.delete()


# TODO: Admin only!!
@client.tree.command()
async def sync(interaction: discord.Interaction):
    """Sync commands globally"""
    await client.tree.sync()
    await interaction.response.send_message("Syncing", ephemeral=True)


client.run(os.environ["RK9_DISCORD_TOKEN"])
