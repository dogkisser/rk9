from peewee import *

db = SqliteDatabase('rk9.sqlite3', pragmas={'journal_mode': 'wal'})

class BaseModel(Model):
    class Meta:
        database = db

class WatchedTags(BaseModel):
    discord_id = BigIntegerField(index=True)
    tags = TextField()
    last_check = DateTimeField(null=True, index=True)

    class Meta:
        # UNIQUE
        indexes = (
            (('discord_id', 'tags'), True),
        )