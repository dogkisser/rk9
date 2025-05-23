import os

import dotenv
from peewee import SqliteDatabase, Model, BigIntegerField, TextField, DateTimeField

dotenv.load_dotenv()

DATA_DIR = os.environ["RK9_DATA_DIR"]

db = SqliteDatabase(f"{DATA_DIR}/rk9.sqlite3", pragmas={"journal_mode": "wal"})


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
