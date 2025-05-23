- replace all the datetime timestamp stuff with an accessor/setter on the database field
- maybe a discord.py check for not following any queries
- maybe `/compact` that minimises the number of separate queries you have by joining them?
- more advanced tag normalisation and deduplication, has to be aware of e621 parenthesis syntax
    though
- follow pool updates (not necessarily new posts)
- more posts may be detected if we look at modified_at instead of created_at as posts are not
    always created with all of their rightful tags. Maybe keep a log of post IDs sent to every
    user; it can be cleared daily (per date:day in the query)