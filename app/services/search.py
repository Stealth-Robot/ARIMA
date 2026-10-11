"""Helpers for building safe SQL LIKE/ILIKE search patterns."""

from sqlalchemy import and_, func, or_, select, true

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


def alias_field(id_col, alias_id_col, alias_name_col, *where):
    """text_match field for names stored in another table; `where` holds its join/filter conditions."""
    return id_col, alias_id_col, alias_name_col, where


def text_match(q, *fields, split_words=True):
    """Every word of q must hit some field, so "song artist" searches match across columns."""
    terms = q.split() if split_words else [q]
    if not terms:
        return true()
    word_clauses = []
    for term in terms:
        pattern = like_contains(term)
        options = []
        for field in fields:
            if isinstance(field, tuple):
                id_col, alias_id_col, alias_name_col, where = field
                options.append(id_col.in_(select(alias_id_col).where(
                    alias_name_col.ilike(pattern, escape=LIKE_ESCAPE), *where)))
            else:
                options.append(field.ilike(pattern, escape=LIKE_ESCAPE))
        word_clauses.append(or_(*options))
    return and_(*word_clauses)
