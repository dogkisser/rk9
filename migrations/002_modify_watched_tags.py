from peewee import BigIntegerField


def migrate(migrator, database, **kwargs):
    WatchedTags = migrator.orm["watchedtags"]

    migrator.add_fields(WatchedTags, posts_sent=BigIntegerField(default=0))
