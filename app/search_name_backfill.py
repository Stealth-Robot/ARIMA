"""One-off startup migration: fill the hidden accent-folded search columns for rows written before they existed.

Called from run_startup_migrations(); delete this file and its call once it has run in production.
"""
import logging

from app.services.search import search_name_for

logger = logging.getLogger(__name__)

_TABLES = (
    ('artist', 'name', 'search_name'),
    ('artist_alt_name', 'name', 'search_name'),
    ('song', 'name', 'search_name'),
    ('song_alias', 'name', 'search_name'),
    ('album', 'name', 'search_name'),
    ('album_alt_name', 'name', 'search_name'),
    ('misc_artist', 'name', 'search_name'),
    ('misc_artist_alt_name', 'name', 'search_name'),
    ('changelog', 'description', 'search_description'),
)


def backfill_search_names(db):
    """Write the folded copy wherever it differs from what is stored, so later runs are no-ops."""
    from app.migrations import create_last_updated_triggers
    dropped = False
    for table, source, target in _TABLES:
        rows = db.session.execute(db.text(f'SELECT id, {source}, {target} FROM {table}')).all()
        updates = [{'v': want, 'id': rid} for rid, value, have in rows if (want := search_name_for(value)) != have]
        if not updates:
            continue
        if table in ('artist', 'song', 'album'):
            # A hidden search column isn't an edit, so it must not bump last_updated.
            db.session.execute(db.text(f'DROP TRIGGER IF EXISTS trg_{table}_last_updated'))
            dropped = True
        db.session.execute(db.text(f'UPDATE {table} SET {target} = :v WHERE id = :id'), updates)
        logger.info('Backfilled %s.%s for %d rows', table, target, len(updates))
    if dropped:
        create_last_updated_triggers(db)
