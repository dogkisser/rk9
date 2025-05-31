import os
from datetime import datetime, timezone
from pathlib import Path

import dotenv
from peewee import SqliteDatabase, Model, Field, BigIntegerField, TextField
from peewee_migrate import Router

dotenv.load_dotenv()

DATA_DIR = os.environ["RK9_DATA_DIR"]

db = SqliteDatabase(
    f"{DATA_DIR}/rk9.sqlite3", pragmas={"journal_mode": "wal", "synchronous": "normal"}
)
router = Router(db, migrate_dir=Path(__file__).absolute().parent.joinpath("migrations"))


class UtcDateTimeField(Field):
    field_type = "text"

    def db_value(self, value):
        return str(value.replace(tzinfo=None))

    def python_value(self, value):
        return datetime.fromisoformat(value).replace(tzinfo=timezone.utc)


class BaseModel(Model):
    class Meta:
        database = db


class WatchedTags(BaseModel):
    discord_id = BigIntegerField(index=True)
    tags = TextField()
    last_check = UtcDateTimeField(index=True)
    posts_sent = BigIntegerField(default=0)

    class Meta:
        # UNIQUE
        indexes = ((("discord_id", "tags"), True),)


class PrefixTags(BaseModel):
    discord_id = BigIntegerField(index=True, unique=True)
    tags = TextField()


class BlacklistedTags(BaseModel):
    discord_id = BigIntegerField(index=True)
    tag = TextField()

    class Meta:
        # UNIQUE
        indexes = ((("discord_id", "tag"), True),)


router.run()
