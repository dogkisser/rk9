from datetime import datetime

import discord
from discord.utils import escape_markdown


def build_embed_from_post(post: dict) -> discord.Embed:
    posted = datetime.fromisoformat(post["created_at"])
    # post['file']['url'] is null if the post is on the global blacklist, but all the
    # other information is intact. we reconstruct the url ourself to side-step.
    img_hash = post["file"]["md5"]
    # try to use the sample if it exists b/c its always a jpg; discord can't embed videos
    path = "/data/sample/" if post["sample"]["has"] else "/data/"
    ext = "jpg" if post["sample"]["has"] else post["file"]["ext"]
    url = f"https://static1.e621.net{path}{img_hash[0:2]}/{img_hash[2:4]}/{img_hash}.{ext}"
    description = post["description"][:150] + (post["description"][150:] and "..")
    embed = discord.Embed(
        title=f"#{post['id']}",
        url=f"https://e621.net/posts/{post['id']}",
        description=escape_markdown(description),
        colour=0x1F2F56,
        timestamp=posted,
    )
    embed.set_image(url=url)
    embed.set_footer(text="/rk9/ • 👎 to remove")

    if post["file"]["ext"] in ["webm", "mp4"]:
        embed.add_field(name=":play_pause: Animated", value="", inline=False)

    author = ", ".join(post["tags"]["artist"])
    if author:
        embed.set_author(name=author)

    return embed
