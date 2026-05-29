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

        # 0. Create any missing tables
        # Clean up submission_old if left behind by a failed migration
        try:
            row = db.session.execute(db.text(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='submission_old'"
            )).fetchone()
            if row:
                db.session.execute(db.text('DROP TABLE IF EXISTS submission_old'))
                logger.info('Cleaned up leftover submission_old table')
        except Exception:
            pass

        db.create_all()

        # 0b. Add any new submission columns
        from app.models.submission import Submission
        existing_sub_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('submission')"))}
        if existing_sub_cols:
            for col in Submission.__table__.columns:
                if col.name not in existing_sub_cols:
                    col_type = 'INTEGER' if 'Integer' in str(col.type) else 'TEXT'
                    db.session.execute(db.text(f'ALTER TABLE submission ADD COLUMN {col.name} {col_type}'))
                    logger.info('Added missing submission column: %s', col.name)

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

        # 1a'. Add owner/maintainer FK columns on artist
        existing_artist_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('artist')"))}
        for col_name in ('owner_id', 'maintainer_id'):
            if col_name not in existing_artist_cols:
                db.session.execute(db.text(f'ALTER TABLE artist ADD COLUMN {col_name} INTEGER'))
                logger.info('Added artist column: %s', col_name)

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

        # Backfill edit_buttons: convert empty default [] to __all__ sentinel
        if 'edit_buttons' in existing_settings_cols:
            db.session.execute(db.text(
                """UPDATE user_settings SET edit_buttons = '["__all__"]' WHERE edit_buttons = '[]'"""
            ))

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

        # 4. Ensure all changelog types exist
        from app.models.lookups import ChangelogType
        for id_, name in [(0, 'Song'), (1, 'Album'), (2, 'Artist'), (3, 'Legacy'), (4, 'Rating'), (5, 'Link')]:
            if not db.session.get(ChangelogType, id_):
                db.session.add(ChangelogType(id=id_, type=name))
                logger.info('Added changelog type: %s', name)

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

        # 6b. Add misc owner/maintainer columns on rules
        existing_rules_cols = {row[1] for row in db.session.execute(db.text("PRAGMA table_info('rules')"))}
        for col_name in ('misc_owner_id', 'misc_maintainer_id'):
            if col_name not in existing_rules_cols:
                db.session.execute(db.text(f'ALTER TABLE rules ADD COLUMN {col_name} INTEGER'))
                logger.info('Added rules column: %s', col_name)

        # 7. Misc overhaul: create new tables, backfill song genres from albums
        _migrate_misc_overhaul()

        # 8. Parse (feat/with/ft/w/) from real artist song titles into misc_artist
        _migrate_collab_credits()

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


def _migrate_misc_overhaul():
    """Idempotent migration for the misc overhaul.

    1. Backfills song_genres from album_genres for misc subunit songs
    2. Parses artist names from song name parentheses, creates misc_artist records
    3. Cleans song names (strips artist parens)
    4. Removes old genre-album scaffolding
    5. Cleans up subunit artist records
    """
    import re
    from app.models.music import Artist, ArtistArtist, ArtistSong, AlbumSong, Album, Song

    existing_sg = db.session.execute(db.text(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='song_genres'"
    )).fetchone()
    if not existing_sg:
        return

    misc = Artist.query.filter_by(name='Misc. Artists').first()
    if not misc:
        return

    subunit_ids = [r.artist_2 for r in ArtistArtist.query.filter_by(
        artist_1=misc.id, relationship=0
    ).all()]
    if not subunit_ids:
        return

    # Step 1: Backfill song_genres from album_genres
    already_backfilled = db.session.execute(db.text(
        'SELECT COUNT(*) FROM song_genres'
    )).scalar()

    if already_backfilled == 0:
        backfill_count = db.session.execute(db.text(
            'INSERT OR IGNORE INTO song_genres (song_id, genre_id) '
            'SELECT DISTINCT als.song_id, ag.genre_id '
            'FROM album_song als '
            'JOIN album_genres ag ON ag.album_id = als.album_id '
            'JOIN artist_song ars ON ars.song_id = als.song_id '
            'WHERE ars.artist_id IN :subunit_ids'
        ).bindparams(db.bindparam('subunit_ids', expanding=True)), {
            'subunit_ids': subunit_ids,
        }).rowcount
        logger.info('Backfilled %d song_genres rows from misc subunit albums', backfill_count)

    # Step 2: Parse artist names and create misc_artist records
    existing_sma = db.session.execute(db.text(
        'SELECT COUNT(*) FROM song_misc_artist'
    )).scalar()

    if existing_sma == 0:
        subunit_map = {}
        for sid in subunit_ids:
            sub = db.session.get(Artist, sid)
            if sub:
                subunit_map[sid] = sub

        paren_re = re.compile(r'^(.+?)\s*\(([^)]*)\)\s*$')
        ma_cache = {}
        songs_parsed = 0
        artists_created = 0

        def _get_or_create_ma(name, country_id):
            nonlocal artists_created
            key = (name.lower(), country_id)
            if key in ma_cache:
                return ma_cache[key]
            row = db.session.execute(db.text(
                'SELECT id FROM misc_artist WHERE LOWER(name) = LOWER(:name) AND country_id = :cid'
            ), {'name': name, 'cid': country_id}).fetchone()
            if row:
                ma_cache[key] = row[0]
                return row[0]
            db.session.execute(db.text(
                'INSERT INTO misc_artist (name, country_id) VALUES (:name, :cid)'
            ), {'name': name, 'cid': country_id})
            ma_id = db.session.execute(db.text(
                'SELECT id FROM misc_artist WHERE LOWER(name) = LOWER(:name) AND country_id = :cid'
            ), {'name': name, 'cid': country_id}).scalar()
            ma_cache[key] = ma_id
            artists_created += 1
            return ma_id

        for sub_id, sub_artist in subunit_map.items():
            song_ids = [r.song_id for r in ArtistSong.query.filter_by(artist_id=sub_id).all()]
            if not song_ids:
                continue
            country_id = sub_artist.country_id

            for song_id in song_ids:
                song = db.session.get(Song, song_id)
                if not song:
                    continue

                m = paren_re.match(song.name)
                if m:
                    clean_name = m.group(1).strip()
                    artist_text = m.group(2).strip()
                    main_names, feat_names = _parse_misc_artists(artist_text)

                    song.name = clean_name

                    for name in main_names:
                        ma_id = _get_or_create_ma(name, country_id)
                        db.session.execute(db.text(
                            'INSERT OR IGNORE INTO song_misc_artist (song_id, misc_artist_id, artist_is_main) '
                            'VALUES (:sid, :maid, 1)'
                        ), {'sid': song_id, 'maid': ma_id})
                    for name in feat_names:
                        ma_id = _get_or_create_ma(name, country_id)
                        db.session.execute(db.text(
                            'INSERT OR IGNORE INTO song_misc_artist (song_id, misc_artist_id, artist_is_main) '
                            'VALUES (:sid, :maid, 0)'
                        ), {'sid': song_id, 'maid': ma_id})
                else:
                    ma_id = _get_or_create_ma(sub_artist.name, country_id)
                    db.session.execute(db.text(
                        'INSERT OR IGNORE INTO song_misc_artist (song_id, misc_artist_id, artist_is_main) '
                        'VALUES (:sid, :maid, 1)'
                    ), {'sid': song_id, 'maid': ma_id})

                songs_parsed += 1

        logger.info('Parsed %d misc songs, created %d misc_artist records', songs_parsed, artists_created)
        db.session.flush()

    # Step 3: Remove old genre-album scaffolding under subunits
    remaining_albums = db.session.execute(db.text(
        'SELECT COUNT(*) FROM album WHERE artist_id IN :sids'
    ).bindparams(db.bindparam('sids', expanding=True)), {'sids': subunit_ids}).scalar()

    if remaining_albums > 0:
        db.session.execute(db.text(
            'DELETE FROM album_song WHERE album_id IN '
            '(SELECT id FROM album WHERE artist_id IN :sids)'
        ).bindparams(db.bindparam('sids', expanding=True)), {'sids': subunit_ids})
        db.session.execute(db.text(
            'DELETE FROM album_genres WHERE album_id IN '
            '(SELECT id FROM album WHERE artist_id IN :sids)'
        ).bindparams(db.bindparam('sids', expanding=True)), {'sids': subunit_ids})
        deleted_albums = db.session.execute(db.text(
            'DELETE FROM album WHERE artist_id IN :sids'
        ).bindparams(db.bindparam('sids', expanding=True)), {'sids': subunit_ids}).rowcount
        logger.info('Removed %d misc genre-album scaffolding records', deleted_albums)

    # Step 4: Clean up subunit artist records
    remaining_rels = ArtistArtist.query.filter_by(artist_1=misc.id, relationship=0).count()
    if remaining_rels > 0:
        for sub_id in subunit_ids:
            db.session.execute(db.text(
                'DELETE FROM artist_song WHERE artist_id = :sid'
            ), {'sid': sub_id})
        ArtistArtist.query.filter_by(artist_1=misc.id, relationship=0).delete()
        db.session.execute(db.text(
            'DELETE FROM artist WHERE id IN :sids'
        ).bindparams(db.bindparam('sids', expanding=True)), {'sids': subunit_ids})
        logger.info('Removed %d misc country subunit artists', len(subunit_ids))

    db.session.flush()


def _strip_collab_markers(name):
    """Remove feat/ft/with/w/ collab markers from a song name."""
    import re
    FEAT_PAREN = r'(?:featuring|feat[.:]*|ft[.,]?|with|w/)'
    name = re.sub(r'\s*[\(\[]\s*' + FEAT_PAREN + r'\s*[^)\]]+[\)\]]', '', name, flags=re.IGNORECASE)
    FEAT_TRAIL = r'(?:featuring|feat[.:]+|feat(?=\s)|ft\.)'
    name = re.sub(r'\s+' + FEAT_TRAIL + r'\s+.+$', '', name, flags=re.IGNORECASE)
    return name.strip()


def _extract_collab_names(song_name):
    """Extract featured artist names from song title collab markers.

    Handles three patterns:
      1. (feat X) / (ft. X) / (with X) / (w/ X) at paren start
      2. (Something feat. X) — marker inside parens but not at start
      3. Title feat. X — trailing marker outside parens
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

    names = []
    matched_spans = set()
    for rx in (paren_start_re, inner_paren_re, trailing_re):
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


def _migrate_collab_credits():
    """Parse collab credits from real artist song titles into misc_artist.

    Creates MiscArtist + SongMiscArtist rows (featured) without modifying song names.
    Skips songs that already have song_misc_artist entries. Idempotent.
    """

    bad = db.session.execute(db.text(
        "SELECT id, name, country_id FROM misc_artist "
        "WHERE name LIKE 'and %' OR name LIKE 'with %'"
    )).fetchall()
    for ma_id, ma_name, ma_cid in bad:
        import re as _re
        clean = _re.sub(r'^(?:and|with)\s+', '', ma_name, flags=_re.IGNORECASE)
        existing = db.session.execute(db.text(
            'SELECT id FROM misc_artist WHERE LOWER(name) = LOWER(:n) AND country_id = :c'
        ), {'n': clean, 'c': ma_cid}).fetchone()
        if existing:
            db.session.execute(db.text(
                'UPDATE song_misc_artist SET misc_artist_id = :new WHERE misc_artist_id = :old'
            ), {'new': existing[0], 'old': ma_id})
            db.session.execute(db.text('DELETE FROM misc_artist WHERE id = :id'), {'id': ma_id})
        else:
            db.session.execute(db.text(
                'UPDATE misc_artist SET name = :n WHERE id = :id'
            ), {'n': clean, 'id': ma_id})

    rows = db.session.execute(db.text(
        "SELECT s.id, s.name, a.country_id "
        "FROM song s "
        "JOIN artist_song ars ON ars.song_id = s.id "
        "JOIN artist a ON a.id = ars.artist_id "
        "LEFT JOIN song_misc_artist sma ON sma.song_id = s.id "
        "WHERE sma.song_id IS NULL "
        "AND (s.name LIKE '%(with %' OR s.name LIKE '%(feat%' "
        "     OR s.name LIKE '%(ft.%' OR s.name LIKE '%(ft %' "
        "     OR s.name LIKE '%(w/ %' OR s.name LIKE '%(w/%' "
        "     OR s.name LIKE '%(featuring %' OR s.name LIKE '%(Feat:%' "
        "     OR s.name LIKE '% feat.%' OR s.name LIKE '% feat %' "
        "     OR s.name LIKE '% ft.%' OR s.name LIKE '% ft %' "
        "     OR s.name LIKE '%Feat. %' OR s.name LIKE '%&Feat.%') "
        "GROUP BY s.id"
    )).fetchall()

    if not rows:
        return

    ma_cache = {}
    artists_created = 0
    links_created = 0

    def _get_or_create_ma(name, country_id):
        nonlocal artists_created
        key = (name.strip().lower(), country_id)
        if key in ma_cache:
            return ma_cache[key]
        row = db.session.execute(db.text(
            'SELECT id FROM misc_artist WHERE LOWER(name) = LOWER(:name) AND country_id = :cid'
        ), {'name': name.strip(), 'cid': country_id}).fetchone()
        if row:
            ma_cache[key] = row[0]
            return row[0]
        db.session.execute(db.text(
            'INSERT INTO misc_artist (name, country_id) VALUES (:name, :cid)'
        ), {'name': name.strip(), 'cid': country_id})
        ma_id = db.session.execute(db.text(
            'SELECT id FROM misc_artist WHERE LOWER(name) = LOWER(:name) AND country_id = :cid'
        ), {'name': name.strip(), 'cid': country_id}).scalar()
        ma_cache[key] = ma_id
        artists_created += 1
        return ma_id

    songs_linked = 0
    for song_id, song_name, country_id in rows:
        names = _extract_collab_names(song_name)
        if not names:
            continue
        songs_linked += 1
        for name in names:
            ma_id = _get_or_create_ma(name, country_id)
            db.session.execute(db.text(
                'INSERT OR IGNORE INTO song_misc_artist (song_id, misc_artist_id, artist_is_main) '
                'VALUES (:sid, :maid, 0)'
            ), {'sid': song_id, 'maid': ma_id})
            links_created += 1
        clean = _strip_collab_markers(song_name)
        if clean != song_name:
            db.session.execute(db.text(
                'UPDATE song SET name = :name WHERE id = :id'
            ), {'name': clean, 'id': song_id})

    logger.info('Collab credits: parsed %d songs, created %d misc artists, %d links',
                songs_linked, artists_created, links_created)

    # Strip collab markers from songs that already have misc_artist links (re-run cleanup)
    dirty = db.session.execute(db.text(
        "SELECT DISTINCT s.id, s.name "
        "FROM song s "
        "JOIN song_misc_artist sma ON sma.song_id = s.id "
        "WHERE s.name LIKE '%(feat%' OR s.name LIKE '%(ft.%' "
        "   OR s.name LIKE '%(ft %' OR s.name LIKE '%(ft,%' "
        "   OR s.name LIKE '%(with %' OR s.name LIKE '%(w/ %' "
        "   OR s.name LIKE '%(w/%' OR s.name LIKE '%(featuring %' "
        "   OR s.name LIKE '%(Feat:%' "
        "   OR s.name LIKE '% feat.%' OR s.name LIKE '% feat %' "
        "   OR s.name LIKE '% ft.%' OR s.name LIKE '% ft %' "
        "   OR s.name LIKE '%Feat. %' OR s.name LIKE '%&Feat.%'"
    )).fetchall()
    cleaned = 0
    for song_id, song_name in dirty:
        clean = _strip_collab_markers(song_name)
        if clean != song_name:
            db.session.execute(db.text(
                'UPDATE song SET name = :name WHERE id = :id'
            ), {'name': clean, 'id': song_id})
            cleaned += 1
    if cleaned:
        logger.info('Stripped collab markers from %d song names', cleaned)

    db.session.flush()
