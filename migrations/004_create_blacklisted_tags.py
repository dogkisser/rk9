from peewee import Model, BigIntegerField, TextField


def migrate(migrator, database, **kwargs):
    @migrator.create_model
    class BlacklistedTags(Model):
        discord_id = BigIntegerField(index=True)
        tag = TextField()

        class Meta:
            # UNIQUE
            indexes = ((("discord_id", "tag"), True),)
