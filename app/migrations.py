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
    """Run auto-migrations on app startup. Safe to call repeatedly.

    ALL migrations live here as idempotent steps — never as standalone
    scripts, never run manually against a database.
    """
    try:
        from app.models.theme import Theme
        from app.models.user import User

        # 0. Create any missing tables
        db.create_all()

        # 0b. Add any new proxy_change columns
        from app.models.proxy_change import ProxyChange
        existing_pc_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('proxy_change')"))}
        if existing_pc_cols:
            for col in ProxyChange.__table__.columns:
                if col.name not in existing_pc_cols:
                    col_type = 'INTEGER' if 'Integer' in str(col.type) else 'TEXT'
                    db.session.execute(db.text(f'ALTER TABLE proxy_change ADD COLUMN {col.name} {col_type}'))
                    logger.info('Added missing proxy_change column: %s', col.name)

        # 1a. Add any new song columns (e.g. note)
        import sqlalchemy
        from app.models.music import Song
        existing_song_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('song')"))}
        for col in Song.__table__.columns:
            if col.name not in existing_song_cols:
                if isinstance(col.type, sqlalchemy.Boolean):
                    db.session.execute(db.text(
                        f'ALTER TABLE song ADD COLUMN {col.name} INTEGER NOT NULL DEFAULT 0'))
                else:
                    db.session.execute(db.text(f'ALTER TABLE song ADD COLUMN {col.name} TEXT'))
                logger.info('Added missing song column: %s', col.name)

        # 1a''. Add any new album columns (e.g. note)
        from app.models.music import Album, Artist
        existing_album_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('album')"))}
        for col in Album.__table__.columns:
            if col.name not in existing_album_cols:
                if isinstance(col.type, sqlalchemy.Boolean):
                    db.session.execute(db.text(
                        f'ALTER TABLE album ADD COLUMN {col.name} INTEGER NOT NULL DEFAULT 0'))
                else:
                    db.session.execute(db.text(f'ALTER TABLE album ADD COLUMN {col.name} TEXT'))
                logger.info('Added missing album column: %s', col.name)

        # 1a'. Add any new artist columns (e.g. owner_id, maintainer_id, spotify_url)
        existing_artist_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('artist')"))}
        for col in Artist.__table__.columns:
            if col.name not in existing_artist_cols:
                if isinstance(col.type, sqlalchemy.Boolean):
                    db.session.execute(db.text(
                        f'ALTER TABLE artist ADD COLUMN {col.name} INTEGER NOT NULL DEFAULT 0'))
                elif isinstance(col.type, sqlalchemy.Integer):
                    db.session.execute(db.text(f'ALTER TABLE artist ADD COLUMN {col.name} INTEGER'))
                else:
                    db.session.execute(db.text(f'ALTER TABLE artist ADD COLUMN {col.name} TEXT'))
                logger.info('Added missing artist column: %s', col.name)

        # 1a'''. Add any new rules columns (e.g. misc_owner_id, misc_image_url)
        from app.models.rules import Rules
        existing_rules_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('rules')"))}
        if existing_rules_cols:
            for col in Rules.__table__.columns:
                if col.name not in existing_rules_cols:
                    if isinstance(col.type, sqlalchemy.Integer):
                        db.session.execute(db.text(f'ALTER TABLE rules ADD COLUMN {col.name} INTEGER'))
                    else:
                        db.session.execute(db.text(f'ALTER TABLE rules ADD COLUMN {col.name} TEXT'))
                    logger.info('Added missing rules column: %s', col.name)

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
                elif isinstance(col.type, sqlalchemy.JSON):
                    db.session.execute(db.text(
                        f"ALTER TABLE user_settings ADD COLUMN {col.name} JSON NOT NULL DEFAULT '{default}'"
                    ))
                else:
                    db.session.execute(db.text(
                        f"ALTER TABLE user_settings ADD COLUMN {col.name} VARCHAR(50) NOT NULL DEFAULT '{default}'"
                    ))
                logger.info('Added missing user_settings column: %s', col.name)

        # 1d. Add any new user columns (e.g. spotify_* OAuth fields)
        existing_user_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('user')"))}
        for col in User.__table__.columns:
            if col.name not in existing_user_cols:
                if isinstance(col.type, sqlalchemy.Boolean):
                    db.session.execute(db.text(
                        f'ALTER TABLE user ADD COLUMN {col.name} INTEGER NOT NULL DEFAULT 0'))
                elif isinstance(col.type, sqlalchemy.Integer):
                    db.session.execute(db.text(f'ALTER TABLE user ADD COLUMN {col.name} INTEGER'))
                else:
                    db.session.execute(db.text(f'ALTER TABLE user ADD COLUMN {col.name} TEXT'))
                logger.info('Added missing user column: %s', col.name)

        # Backfill edit_buttons: convert empty default [] to __all__ sentinel
        if 'edit_buttons' in existing_settings_cols:
            db.session.execute(db.text(
                """UPDATE user_settings SET edit_buttons = '["__all__"]' WHERE edit_buttons = '[]'"""
            ))

        # 1e. Ensure the 'Related' artist relationship lookup row exists (id=2)
        existing_rels = {row[0] for row in db.session.execute(db.text('SELECT id FROM artist_relationship'))}
        if 2 not in existing_rels:
            db.session.execute(db.text("INSERT INTO artist_relationship (id, relationship) VALUES (2, 'Related')"))
            logger.info("Added 'Related' artist relationship lookup row")

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
    except Exception:
        db.session.rollback()
        logger.exception('Startup migration failed (DB may not exist yet)')


def _parse_misc_artists(text):
    """Parse 'Artist1, Artist2 & Artist3 feat. Feat1' into (main[], featured[]).

    Handles commas, ampersands, and feat/ft markers.
    Known band names containing separators are preserved intact.
    """
    import re

    KNOWN_BANDS = {
        'kisida kyodan & the akeboshi rockets',
        'fear, and loathing in las vegas',
    }

    if text.strip().lower() in KNOWN_BANDS:
        return [text.strip()], []

    feat_re = re.compile(r'\s+(?:feat\.?|ft\.?)\s+', re.IGNORECASE)
    with_re = re.compile(r'^(?:with|w/)\s+', re.IGNORECASE)
    parts = feat_re.split(text, maxsplit=1)
    main_part = parts[0].strip()
    feat_part = parts[1].strip() if len(parts) > 1 else ''

    wm = with_re.match(main_part)
    if wm:
        feat_part = main_part[wm.end():].strip() + (', ' + feat_part if feat_part else '')
        main_part = ''

    def _clean(name):
        n = re.sub(r'^(?:and|&)\s+', '', name.strip(), flags=re.IGNORECASE)
        return n.strip()

    def _split(s):
        if not s.strip():
            return []
        if ', ' in s:
            pieces = s.split(', ')
            result = []
            for i, p in enumerate(pieces):
                if i == len(pieces) - 1 and ' & ' in p:
                    result.extend(_clean(sub) for sub in p.split(' & ') if _clean(sub))
                else:
                    if _clean(p):
                        result.append(_clean(p))
            return result
        if ' & ' in s:
            return [_clean(p) for p in s.split(' & ') if _clean(p)]
        return [_clean(s)] if _clean(s) else []

    return _split(main_part), _split(feat_part)


def _extract_collab_names(song_name):
    """Extract featured artist names from song title collab markers.

    Handles these patterns:
      1. (feat X) / (ft. X) / (with X) / (w/ X) at paren start
      2. (Something feat. X) — marker inside parens but not at start
      3. Title feat. X — trailing marker outside parens
      4. (X & Y duet) / (X SOLO) — names before a trailing duet/solo keyword
    Returns a list of artist name strings (may be empty).
    """
    import re
    FEAT_PAREN = r'(?:featuring|feat[.:]*|ft\.?|with|w/)'
    FEAT_TRAIL = r'(?:featuring|feat[.:]+|feat(?=\s)|ft\.)'

    paren_start_re = re.compile(
        r'[\(\[]\s*' + FEAT_PAREN + r'\s*([^)\]]+)[\)\]]', re.IGNORECASE)
    inner_paren_re = re.compile(
        r'[\(\[][^)\]]*?[&\s]' + FEAT_PAREN + r'\s*([^)\]]+)[\)\]]', re.IGNORECASE)
    trailing_re = re.compile(
        r'(?:^|[\s\-])\s*' + FEAT_TRAIL + r'\s*(.+?)(?:\s*\((?!.*' + FEAT_PAREN + r')|\s*$)',
        re.IGNORECASE)
    duet_solo_re = re.compile(
        r'[\(\[]\s*([^)\]]+?)\s+(?:duet|solo)\s*[\)\]]', re.IGNORECASE)

    names = []
    matched_spans = set()
    for rx in (paren_start_re, inner_paren_re, trailing_re, duet_solo_re):
        for m in rx.finditer(song_name):
            if m.span() in matched_spans:
                continue
            artist_text = m.group(1).strip().rstrip(')')
            if not artist_text:
                continue
            matched_spans.add(m.span())
            main, feat = _parse_misc_artists(artist_text)
            names.extend(feat if feat else main)
    seen = set()
    deduped = []
    for n in names:
        n = n.strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            deduped.append(n)
    return deduped


def _tidy_title(t):
    """Collapse the artifacts left after a name is removed from a title marker."""
    import re
    t = re.sub(r'[\(\[]\s*[\)\]]', '', t)     # drop now-empty () or []
    t = re.sub(r'([\(\[])\s+', r'\1', t)      # no space just inside an open bracket
    t = re.sub(r'\s+([\)\]])', r'\1', t)      # no space just inside a close bracket
    t = re.sub(r'\s{2,}', ' ', t)             # collapse runs of spaces
    t = re.sub(r'\s*[-–]\s*$', '', t)         # drop a dangling trailing dash
    return t.strip()


def _strip_collab_name(song_name, name):
    """Remove one collaborator's credit from a song title's feat/with/duet/solo marker.

    Mirrors the markers _extract_collab_names detects. If `name` was the only artist in
    the marker, the whole marker is removed; if other artists are co-credited there, only
    `name` is dropped and the rest are kept. Returns the cleaned title (unchanged if the
    name isn't found in any marker).
    """
    import re
    name = (name or '').strip()
    if not name:
        return song_name
    FEAT_PAREN = r'(?:featuring|feat[.:]*|ft\.?|with|w/)'
    FEAT_TRAIL = r'(?:featuring|feat[.:]+|feat(?=\s)|ft\.)'
    paren_start_re = re.compile(r'[\(\[]\s*' + FEAT_PAREN + r'\s*([^)\]]+)[\)\]]', re.IGNORECASE)
    inner_paren_re = re.compile(r'[\(\[][^)\]]*?[&\s]' + FEAT_PAREN + r'\s*([^)\]]+)[\)\]]', re.IGNORECASE)
    trailing_re = re.compile(
        r'(?:^|[\s\-])\s*' + FEAT_TRAIL + r'\s*(.+?)(?:\s*\((?!.*' + FEAT_PAREN + r')|\s*$)', re.IGNORECASE)
    duet_solo_re = re.compile(r'[\(\[]\s*([^)\]]+?)\s+(?:duet|solo)\s*[\)\]]', re.IGNORECASE)

    for rx in (paren_start_re, inner_paren_re, duet_solo_re, trailing_re):
        for m in rx.finditer(song_name):
            inner = m.group(1).strip().rstrip(')')
            main, feat = _parse_misc_artists(inner)
            combined = main + feat
            if not any(c.strip().lower() == name.lower() for c in combined):
                continue
            remaining = [c for c in combined if c.strip().lower() != name.lower()]
            if remaining:
                s1, e1 = m.span(1)
                new = song_name[:s1] + ' & '.join(remaining) + song_name[e1:]
            else:
                new = song_name[:m.start()] + song_name[m.end():]
            return _tidy_title(new)
    return song_name
