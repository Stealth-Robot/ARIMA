"""Helpers for building safe SQL LIKE/ILIKE search patterns."""

import unicodedata

from sqlalchemy import and_, func, or_, select, true

# Letters NFKD leaves whole; mirrored by FOLD_MAP in static/js/core.js.
_FOLD_MAP = str.maketrans({
    'ø': 'o', 'Ø': 'O', 'ß': 'ss', 'æ': 'ae', 'Æ': 'AE', 'œ': 'oe', 'Œ': 'OE', 'ł': 'l', 'Ł': 'L',
    'đ': 'd', 'Đ': 'D', 'ð': 'd', 'Ð': 'D', 'þ': 'th', 'Þ': 'Th', 'ı': 'i',
})

# Hidden search-only copies of a column, kept in sync by the models; never displayed.
SEARCH_COLUMNS = {'name': 'search_name', 'description': 'search_description'}


def _is_latin_or_symbol(ch):
    """True for Latin letters and non-letters; False for kana, Hangul, Han and other scripts' letters."""
    if not ch.isalpha():
        return True
    name = unicodedata.name(ch, '')
    return name.startswith(('LATIN', 'MODIFIER LETTER')) or ch in 'ªº'


def fold_accents(text):
    """Fold accents and compatibility symbols to plain characters (Bahía -> Bahia, ℃ -> °C, Ⅱ -> II).

    Only Latin letters and symbols are folded, so kana, Hangul and Han pass through untouched.
    """
    if not text:
        return text
    out = []
    for ch in unicodedata.normalize('NFC', text).translate(_FOLD_MAP):
        if _is_latin_or_symbol(ch):
            out.append(''.join(c for c in unicodedata.normalize('NFKD', ch) if not unicodedata.combining(c)))
        else:
            out.append(ch)
    return ''.join(out)


def search_name_for(name):
    """The hidden search copy of a name or text: None when folding changes nothing (e.g. fully native names)."""
    folded = fold_accents(name)
    return folded if folded != name else None

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


def search_column(field):
    """The column to search for `field`: its hidden folded copy, falling back to the field itself."""
    sibling = getattr(getattr(field, 'class_', None), SEARCH_COLUMNS.get(getattr(field, 'key', None), ''), None)
    return func.coalesce(sibling, field) if sibling is not None else field


def name_match(field, term, ignore_punct=False):
    """ilike `term` against a column, also matching accent-folded ("bahia" finds "Bahía", and vice versa)."""
    raw, folded = (strip_punct(term), strip_punct(fold_accents(term))) if ignore_punct else (term, fold_accents(term))
    hidden = search_column(field)
    hidden = strip_punct_sql(hidden) if ignore_punct else hidden
    match = hidden.ilike(like_contains(folded), escape=LIKE_ESCAPE)
    if raw == folded:
        return match
    # An accented query still has to hit native-script names, which keep no folded copy ("huā" -> "花 Huā").
    plain = strip_punct_sql(field) if ignore_punct else field
    return or_(plain.ilike(like_contains(raw), escape=LIKE_ESCAPE), match)


def text_match(q, *fields, split_words=True):
    """Every word of q must hit some field, so "song artist" searches match across columns."""
    terms = q.split() if split_words else [q]
    if not terms:
        return true()
    word_clauses = []
    for term in terms:
        options = []
        for field in fields:
            if isinstance(field, tuple):
                id_col, alias_id_col, alias_name_col, where = field
                options.append(id_col.in_(select(alias_id_col).where(
                    name_match(alias_name_col, term), *where)))
            else:
                options.append(name_match(field, term))
        word_clauses.append(or_(*options))
    return and_(*word_clauses)
