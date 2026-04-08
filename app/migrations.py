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
        db.create_all()

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

        # 1c. Add any new user_settings columns
        from app.models.user import UserSettings
        import sqlalchemy
        existing_settings_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('user_settings')"))}
        for col in UserSettings.__table__.columns:
            if col.name not in existing_settings_cols:
                default = (col.server_default.arg if col.server_default else '').replace("'", "''")
                if isinstance(col.type, sqlalchemy.Boolean):
                    db.session.execute(db.text(
                        f"ALTER TABLE user_settings ADD COLUMN {col.name} INTEGER NOT NULL DEFAULT {default}"
                    ))
                else:
                    db.session.execute(db.text(
                        f"ALTER TABLE user_settings ADD COLUMN {col.name} VARCHAR(50) NOT NULL DEFAULT '{default}'"
                    ))
                logger.info('Added missing user_settings column: %s', col.name)

        # 2. Create missing personal Theme rows (skip guest/system users with no email)
        existing_user_ids = {t.user_id for t in Theme.query.filter(Theme.user_id.isnot(None)).all()}
        missing = User.query.filter(
            ~User.id.in_(existing_user_ids),
            User.email.isnot(None),
        ).all() if existing_user_ids else User.query.filter(User.email.isnot(None)).all()
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

        # 3b. Remove personal themes for guest/system users before backfilling
        db.session.flush()
        deleted = db.session.execute(db.text(
            'DELETE FROM theme WHERE user_id IN (SELECT id FROM user WHERE email IS NULL)'
        )).rowcount
        if deleted:
            db.session.expire_all()
            logger.info('Removed %d guest/system theme rows', deleted)

        # 3c. Backfill NULL values in personal themes from Dark theme
        dark_theme = db.session.get(Theme, 1)
        if dark_theme:
            personal_themes = Theme.query.filter(Theme.user_id.isnot(None)).all()
            for pt in personal_themes:
                for col in colour_cols:
                    if getattr(pt, col) is None:
                        dark_val = getattr(dark_theme, col)
                        if dark_val:
                            setattr(pt, col, dark_val)

        db.session.commit()

        # 4. Add missing indexes
        for idx_sql in [
            'CREATE INDEX IF NOT EXISTS ix_artist_artist_relationship ON artist_artist (relationship)',
            'CREATE INDEX IF NOT EXISTS ix_rating_user_id ON rating (user_id)',
        ]:
            db.session.execute(db.text(idx_sql))

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

        # 7. Ensure Misc. Artists has country subunits and genre albums
        from app.services.artist import sync_misc_artist_stubs
        sync_misc_artist_stubs()

        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception('Startup migration failed (DB may not exist yet)')
