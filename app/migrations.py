import logging

from app.extensions import db

logger = logging.getLogger(__name__)


def create_last_updated_triggers(database):
    """Create SQLite triggers that auto-set last_updated on row updates."""
    for table in ('artist', 'song', 'album', 'user'):
        database.session.execute(database.text(f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_last_updated
            AFTER UPDATE ON {table}
            BEGIN
                UPDATE {table} SET last_updated = strftime('%Y-%m-%dT%H:%M:%S', 'now')
                WHERE id = NEW.id;
            END;
        """))
    database.session.commit()


def run_startup_migrations():
    """Run auto-migrations on app startup. Safe to call repeatedly."""
    try:
        from app.models.theme import Theme
        from app.models.user import User

        # 0. Create any missing tables (e.g. update)
        # If the submission table exists with an old schema, drop and recreate it
        existing_sub_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('submission')"))}
        if existing_sub_cols and 'type' not in existing_sub_cols:
            db.session.execute(db.text('DROP TABLE IF EXISTS submission'))
            logger.info('Dropped old submission table (schema mismatch)')

        db.create_all()

        # 0b. Add any new submission columns
        existing_sub_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('submission')"))}
        for col in ('entity_name', 'artist_id', 'artist_name', 'album_id'):
            if existing_sub_cols and col not in existing_sub_cols:
                col_type = 'INTEGER' if col.endswith('_id') else 'TEXT'
                db.session.execute(db.text(f'ALTER TABLE submission ADD COLUMN {col} {col_type}'))
                logger.info('Added missing submission column: %s', col)

        # 1a. Add any new song columns (e.g. note)
        from app.models.music import Song
        existing_song_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('song')"))}
        for col in Song.__table__.columns:
            if col.name not in existing_song_cols:
                db.session.execute(db.text(f'ALTER TABLE song ADD COLUMN {col.name} TEXT'))
                logger.info('Added missing song column: %s', col.name)

        # 1b. Add any new theme colour columns
        existing = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('theme')"))}
        for col in Theme.__table__.columns:
            if col.name not in existing and col.name not in ('id', 'name', 'user_id'):
                db.session.execute(db.text(f'ALTER TABLE theme ADD COLUMN {col.name} TEXT'))
                logger.info('Added missing theme column: %s', col.name)

        # 2. Create missing personal Theme rows
        existing_user_ids = {t.user_id for t in Theme.query.filter(Theme.user_id.isnot(None)).all()}
        missing = User.query.filter(~User.id.in_(existing_user_ids)).all() if existing_user_ids else User.query.all()
        for u in missing:
            db.session.add(Theme(user_id=u.id))
            logger.info('Created missing theme for user: %s', u.username)

        # 3. Backfill NULL values in system themes
        from app.seed import CLASSIC_THEME, DARK_THEME
        colour_cols = [c.name for c in Theme.__table__.columns
                       if c.name not in ('id', 'name', 'user_id')]
        defaults = {0: CLASSIC_THEME, 1: DARK_THEME}
        for theme_id, theme_name in ((0, 'Classic'), (1, 'Dark')):
            theme = db.session.get(Theme, theme_id)
            if theme:
                for col in colour_cols:
                    if getattr(theme, col) is None:
                        default = defaults[theme_id].get(col)
                        if default:
                            setattr(theme, col, default)
                            logger.info('Backfilled %s theme column %s = %s', theme_name, col, default)

        # 4. Add missing indexes
        for idx_sql in [
            'CREATE INDEX IF NOT EXISTS ix_artist_artist_relationship ON artist_artist (relationship)',
            'CREATE INDEX IF NOT EXISTS ix_rating_user_id ON rating (user_id)',
        ]:
            db.session.execute(db.text(idx_sql))

        # 5. Remove personal themes for guest/system users (no email)
        deleted = db.session.execute(db.text(
            'DELETE FROM theme WHERE user_id IN (SELECT id FROM user WHERE email IS NULL)'
        )).rowcount
        if deleted:
            logger.info('Removed %d guest/system theme rows', deleted)

        # 6. Ensure all seeded UpdateType rows exist
        from app.models.lookups import UpdateType
        for id_, type_, desc in [
            (1, 'Feature', 'New Feature'),
            (2, 'Bugfix', 'Bug Fix'),
            (3, 'Style', 'Themes And Layout Changes'),
            (4, 'Perf.', 'Performance Improvement'),
            (5, 'Code', 'Code-only changes, cleanup/refactors, no change for users'),
        ]:
            if not db.session.get(UpdateType, id_):
                db.session.add(UpdateType(id=id_, type=type_, description=desc))
                logger.info('Added missing update type: %s', type_)

        # 7. Re-render changelog description_html with ID-based links
        from app.models.changelog import Changelog
        from app.services.audit import build_description_html
        from app.models.music import Song, Album
        changelogs = Changelog.query.all()
        rerendered = 0
        for cl in changelogs:
            a = db.session.get(Artist, cl.artist_id) if cl.artist_id else None
            al = db.session.get(Album, cl.album_id) if cl.album_id else None
            s = db.session.get(Song, cl.song_id) if cl.song_id else None
            # Infer artist from album if not set on changelog
            if not a and al and al.artist_id:
                a = db.session.get(Artist, al.artist_id)
            new_html = build_description_html(cl.description, artist=a, album=al, song=s)
            if new_html != cl.description_html:
                cl.description_html = new_html
                rerendered += 1
        if rerendered:
            logger.info('Re-rendered %d changelog entries with ID-based links', rerendered)

        # 8. Ensure Misc. Artists has country subunits and genre albums
        from app.services.artist import sync_misc_artist_stubs
        sync_misc_artist_stubs()

        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('Startup migration failed (DB may not exist yet)')
