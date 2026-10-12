"""One-off startup migration: tag songs as anime Opening/Ending/Insert from their notes.

Called from run_startup_migrations(); delete this file and its call once it has run in production.
"""
import logging
import re

logger = logging.getLogger(__name__)

_THEME_WORD = re.compile(
    r'\b(?:(OP|ED|Op|Ed|op|ed)|(opening|ending|insert))(?:\s*(?:theme|song))?(?:\s*#?\s*(\d{1,2}))?\b', re.I)
_THEME_CODE = {'op': 'op', 'ed': 'ed', 'opening': 'op', 'ending': 'ed', 'insert': 'in'}


def _theme_from_note(note):
    """Return (theme_type, number or None) when a note names exactly one theme kind, else None."""
    if re.match(r'\s*cover of\b', note, re.I):
        return None
    found = []
    for m in _THEME_WORD.finditer(note):
        if m.group(1) and m.group(1) not in ('OP', 'ED', 'Op', 'Ed', 'op', 'ed'):
            continue
        after = note[m.end():]
        # "Ed Sheeran" is a name, and "the opening of the shop" is not a theme song.
        if m.group(1) == 'Ed' and re.match(r'\s+[A-Z]', after):
            continue
        if m.group(2) and re.match(r'\s+of\b', after, re.I):
            continue
        word = (m.group(1) or m.group(2)).lower()
        found.append((_THEME_CODE[word], int(m.group(3)) if m.group(3) else None))
    if len({k for k, _ in found}) != 1:
        return None
    nums = {n for _, n in found if n}
    return found[0][0], (nums.pop() if len(nums) == 1 else None)


def backfill_song_themes(db):
    """Tag songs from their notes. Runs only while no song has a theme yet, so later edits are never overwritten."""
    if db.session.execute(db.text('SELECT 1 FROM song WHERE theme_type IS NOT NULL LIMIT 1')).first():
        return
    tagged = 0
    for sid, note in db.session.execute(db.text('SELECT id, note FROM song WHERE note IS NOT NULL')).all():
        theme = _theme_from_note(note)
        if theme:
            db.session.execute(db.text('UPDATE song SET theme_type = :t, theme_number = :n WHERE id = :id'),
                               {'t': theme[0], 'n': theme[1], 'id': sid})
            tagged += 1
    logger.info('Backfilled theme_type for %d songs from their notes', tagged)
