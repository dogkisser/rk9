from peewee import SqliteDatabase, Model, BigIntegerField, TextField, DateTimeField

db = SqliteDatabase("data/rk9.sqlite3", pragmas={"journal_mode": "wal"})

class BaseModel(Model):
    class Meta:
        database = db


class WatchedTags(BaseModel):
    discord_id = BigIntegerField(index=True)
    tags = TextField()
    last_check = DateTimeField(index=True)

    class Meta:
        # UNIQUE
        indexes = ((("discord_id", "tags"), True),)


class PrefixTags(BaseModel):
    discord_id = BigIntegerField(index=True, unique=True)
    tags = TextField()
