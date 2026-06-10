"""Helpers for building safe SQL LIKE/ILIKE search patterns."""

# Backslash escape char for LIKE patterns. Pass as `escape=LIKE_ESCAPE` to .ilike().
LIKE_ESCAPE = '\\'


def like_contains(term):
    """Escape LIKE wildcards in `term` and wrap it as a contains pattern (%term%).

    Without escaping, a user typing % or _ would match every row / any single
    char. Escape the backslash first, then % and _, and use `escape=LIKE_ESCAPE`
    so SQLite treats them as literal characters.
    """
    escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'
