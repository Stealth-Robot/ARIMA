"""Helpers for building safe SQL LIKE/ILIKE search patterns."""

from sqlalchemy import func

# Backslash escape char for LIKE patterns. Pass as `escape=LIKE_ESCAPE` to .ilike().
LIKE_ESCAPE = '\\'

# Characters stripped from both the query and the matched columns when the
# "ignore punctuation" search setting is on, so e.g. "dont" matches "Don't".
PUNCT_CHARS = "'’‘`´\".,!?():;[]{}&/\\|*#@~+=…·-–—“”"


def strip_punct(text):
    """Remove punctuation characters from a Python string."""
    for ch in PUNCT_CHARS:
        text = text.replace(ch, '')
    return text


def strip_punct_sql(col):
    """Wrap a column/expression so punctuation is removed in-query.

    Uses the `strip_punct` SQLite user-defined function (registered on connect)
    rather than dozens of nested REPLACE() calls, which overflow SQLite's parser.
    """
    return func.strip_punct(col)


def like_contains(term):
    """Escape LIKE wildcards in `term` and wrap it as a contains pattern (%term%).

    Without escaping, a user typing % or _ would match every row / any single
    char. Escape the backslash first, then % and _, and use `escape=LIKE_ESCAPE`
    so SQLite treats them as literal characters.
    """
    escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'
