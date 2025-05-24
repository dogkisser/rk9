from database import UtcDateTimeField

def migrate(migrator, database, **kwargs):
    WatchedTags = migrator.orm["watchedtags"]

    migrator.change_fields(WatchedTags, last_check=UtcDateTimeField(index=True))