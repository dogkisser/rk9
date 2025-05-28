from cogs.blacklist import Blacklist
from cogs.prefix import Prefix
from cogs.query import Query


async def add_all(bot):
    for cog in [Blacklist, Prefix, Query]:
        await bot.add_cog(cog(bot))
