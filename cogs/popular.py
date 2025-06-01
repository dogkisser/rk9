from database import db, UserSettings
import util

import datetime
import logging

import discord
from discord import app_commands
import discord.ext.tasks as tasks
import discord.ext.commands as commands
import aiohttp


class Popular(commands.GroupCog, name="popular"):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.check_popular.start()

    @app_commands.command()
    async def subscribe(self, interaction: discord.Interaction, to: bool):
        """
        Toggle being sent the top posts of the day.
        """
        with db.atomic():
            i, _ = UserSettings.get_or_create(discord_id=interaction.user.id)
            i.subscribed_to_popular = to
            i.save()

        await interaction.response.send_message("Done", ephemeral=True)

    @tasks.loop(time=datetime.time(hour=23, minute=30))
    async def check_popular(self):
        await self.bot.wait_until_ready()

        headers = {"user-agent": "github.com/dogkisser/rk9"}

        async with (
            self.bot.e6_rate_limit,
            aiohttp.ClientSession(headers=headers) as session,
            session.get(
                "https://e621.net/posts.json?tags=order:popular date:day limit:30"
            ) as response,
        ):
            if response.status != 200:
                logging.warn(f"response != 200: {response}")

            response = await response.json()
            posts = response["posts"]

        embeds = [
            util.build_embed_from_post(post).add_field(name="Popular today", value="", inline=False)
            for post in posts
        ]

        subscribed = UserSettings.select().where(UserSettings.subscribed_to_popular == True)  # noqa: E712
        for settings in subscribed:
            user = self.bot.get_user(settings.discord_id)

            if not (channel := user.dm_channel):
                channel = await user.create_dm()

            for embed in embeds:
                await channel.send(embed=embed)
