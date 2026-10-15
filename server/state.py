"""Live, shared host state. Never hot-reloaded, so it survives code edits."""
ONLINE: dict = {}   # screen name (lowercase) -> server.Link
ROOMS: dict = {}    # room name -> {"title": str, "members": [Link, ...]}
CACHE: dict = {}    # content cache: key -> (fetched_at, value)
