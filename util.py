import string


class TagError(ValueError):
    pass


def flatten(xss):
    return [x for xs in xss for x in xs]


def normalise_tags(tags: str) -> str:
    if not all(c in string.printable for c in tags):
        raise TagError("tags contain characters disallowed by e621")

    if len(tags.split()) > 40:
        raise TagError("too many tags in query (> 40)")

    return tags.lower()
