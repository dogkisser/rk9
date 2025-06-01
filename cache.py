from peewee import SqliteDatabase, Model, BigIntegerField

db = SqliteDatabase(":memory:")


class BaseModel(Model):
    class Meta:
        database = db


class SeenPosts(BaseModel):
    discord_id = BigIntegerField(index=True)
    post_id = BigIntegerField(index=True)

    class Meta:
        # UNIQUE
        indexes = ((("discord_id", "post_id"), True),)


db.connect()
db.create_tables([SeenPosts])
