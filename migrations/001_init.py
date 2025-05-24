from peewee import Model, BigIntegerField, TextField, DateTimeField


def migrate(migrator, database, **kwargs):
    @migrator.create_model
    class WatchedTags(Model):
        discord_id = BigIntegerField(index=True)
        tags = TextField()
        last_check = DateTimeField(index=True)

        class Meta:
            # UNIQUE
            indexes = ((("discord_id", "tags"), True),)

    @migrator.create_model
    class PrefixTags(Model):
        discord_id = BigIntegerField(index=True, unique=True)
        tags = TextField()
