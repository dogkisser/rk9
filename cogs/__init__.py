from cogs.blacklist import Blacklist
from cogs.prefix import Prefix
from cogs.query import Query
from cogs.popular import Popular


async def add_all(bot):
    for cog in [Blacklist, Prefix, Query, Popular]:
        await bot.add_cog(cog(bot))
