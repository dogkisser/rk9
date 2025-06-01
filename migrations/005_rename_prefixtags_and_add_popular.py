from peewee import BooleanField


def migrate(migrator, database, **kwargs):
    prefix_tags = migrator.orm["prefixtags"]

    migrator.rename_field(prefix_tags, "tags", "prefix_tags")
    migrator.add_fields(prefix_tags, subscribed_to_popular=BooleanField(default=False))
    migrator.rename_table(prefix_tags, "UserSettings")
