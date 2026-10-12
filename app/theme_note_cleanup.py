"""One-off startup migration: strip the Opening/Ending/Insert wording from song notes now that songs carry a theme tag.

Called from run_startup_migrations(); delete this file and its call once it has run in production.
"""
import logging
import re

logger = logging.getLogger(__name__)

# Detection is the theme backfill's, unchanged, so only the wording that produced a tag is removed.
_THEME_WORD = re.compile(
    r'\b(?:(OP|ED|Op|Ed|op|ed)|(opening|ending|insert))(?:\s*(?:theme|song))?(?:\s*#?\s*(\d{1,2}))?\b', re.I)
_THEME_CODE = {'op': 'op', 'ed': 'ed', 'opening': 'op', 'ending': 'ed', 'insert': 'in'}
_SEP = r'[\-–—:,/|]+'
_GAP = '\x00'
# "2nd Ending for ..." at the start of a line; mid-line ordinals are usually titles ("Memories Off 2nd OP").
_LEAD_ORDINAL = re.compile(
    r'[ \t]*(?:(\d{1,2})(?:st|nd|rd|th)|(first|second|third|fourth|fifth))(?:[ \t]+official)?[ \t]+', re.I)
_ORDINAL_WORDS = {'first': 1, 'second': 2, 'third': 3, 'fourth': 4, 'fifth': 5}
# The theme regex takes only one of theme/song, so "Theme Song" would leave "Song"; "T heme" is a typo in the data.
_TRAILING_WORDS = re.compile(r'(?:[ \t]+t[ \t]+heme\b)?(?:[ \t]+song\b)?', re.I)


def _theme_matches(note):
    """Return [(theme_type, number or None, match)] when a note names exactly one theme kind, else None."""
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
        found.append((_THEME_CODE[word], int(m.group(3)) if m.group(3) else None, m))
    if len({k for k, _, _ in found}) != 1:
        return None
    return found


def _strip_theme(note, theme_type, theme_number):
    """Return (note without its theme wording, theme_number to set or None), or None to leave the song alone."""
    found = _theme_matches(note)
    # Only strip what the song's tag already says; otherwise the note is the only record of it.
    if not found or found[0][0] != theme_type:
        return None
    if any(n is not None and n != theme_number for _, n, _ in found):
        return None
    out = note
    new_number = None
    for _, _, m in reversed(found):
        before, after = out[:m.start()], out[m.end():]
        after = after[_TRAILING_WORDS.match(after).end():]
        line_before = before.rsplit('\n', 1)[-1]
        om = _LEAD_ORDINAL.fullmatch(line_before)
        if om:
            n = int(om.group(1)) if om.group(1) else _ORDINAL_WORDS[om.group(2).lower()]
            # The ordinal moves into the tag's number, so a song already numbered differently is left alone.
            if (theme_number is not None and n != theme_number) or (new_number is not None and n != new_number):
                return None
            new_number = n if theme_number is None else None
            before, line_before = before[:len(before) - len(line_before)], ''
        connector = re.match(r'[ \t]*(?:for|of|from)\b[ \t]*', after, re.I)
        if connector:
            # "OP for Tower of God" / "New version of OP for X": the connector only made sense with the theme word.
            if not line_before.strip() or re.search(r'\b(?:of|for)\s*$', line_before, re.I):
                after = after[connector.end():]
            else:
                # "Vivy OP for eps 4-6" reads as "Vivy, eps 4-6".
                after = ', ' + after[connector.end():]
        out = before + _GAP + after
    # Tidy only around the removed wording so the rest of the note stays byte-for-byte as written.
    out = re.sub(rf'\([ \t]*{_GAP}[ \t]*\)|\[[ \t]*{_GAP}[ \t]*\]', _GAP, out)
    out = re.sub(rf'[ \t]*{_GAP}[ \t]*(?=[,.;:!?)\]])', '', out)
    lines = []
    for line in out.split('\n'):
        if _GAP in line:
            cr = '\r' if line.endswith('\r') else ''
            line = line.rstrip('\r')
            # "Shippuden - OP 16" and "Bleach-ending 13" lose the dash, "-Shallow Dream- Ending" keeps the title's own.
            line = re.sub(rf'(?:[ \t]+{_SEP}[ \t]*|{_SEP}|[:,/|]+[ \t]*)(?={_GAP})', '', line)
            line = re.sub(rf'(?<={_GAP})(?:[ \t]*{_SEP}[ \t]+|{_SEP})', '', line)
            line = re.sub(rf'^[ \t]*(?:{_GAP}[ \t]*)+|[ \t]*(?:{_GAP}[ \t]*)+$', '', line)
            line = re.sub(rf'[ \t]*(?:{_GAP}[ \t]*)+', ' ', line) + cr
        lines.append(line)
    return '\n'.join(lines).strip(), new_number


def strip_theme_from_notes(db):
    """Remove theme wording from tagged songs' notes; a note left empty becomes NULL."""
    rows = db.session.execute(db.text(
        'SELECT id, note, theme_type, theme_number FROM song WHERE note IS NOT NULL AND theme_type IS NOT NULL')).all()
    changed = 0
    for sid, note, theme_type, theme_number in rows:
        result = _strip_theme(note, theme_type, theme_number)
        if result is None or result[0] == note:
            continue
        new_note, new_number = result
        db.session.execute(db.text('UPDATE song SET note = :n, theme_number = COALESCE(:num, theme_number) WHERE id = :id'),
                           {'n': new_note or None, 'num': new_number, 'id': sid})
        changed += 1
    logger.info('Stripped theme wording from %d song notes', changed)


