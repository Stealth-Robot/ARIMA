from datetime import datetime, timezone

from flask import current_app

from app.extensions import bcrypt
from app.models.lookups import Country, Genre, AlbumType, GroupGender, ArtistRelationship, ChangelogType, UpdateType
from app.models.music import Artist, ArtistArtist, Album, AlbumSong, ArtistSong, album_genres
from app.models.user import Role, User
from app.models.theme import Theme
from app.models.rules import Rules


def _now():
    return datetime.now(timezone.utc).isoformat()


def _hash(password):
    pepper = current_app.config['PEPPER']
    return bcrypt.generate_password_hash(pepper + password).decode('utf-8')


# Classic theme — all 40 columns populated, no NULLs
CLASSIC_THEME = {
    # UI chrome (17)
    'bg_primary': '#FFFFFF',
    'bg_secondary': '#F5F5F5',
    'text_primary': '#1A1A1A',
    'text_secondary': '#6B7280',
    'navbar_bg': '#000000',
    'navbar_text': '#F9FAFB',
    'header_row': '#E5E7EB',
    'promoted_song': '#FFD6F0',
    'gender_female': '#EC4899',
    'gender_male': '#3B82F6',
    'gender_mixed': '#00FF00',
    'gender_anime': '#F59E0B',
    'album_name': '#059669',
    'link': '#2563EB',
    'button_primary': '#2563EB',
    'button_secondary': '#6B7280',
    'border': '#D1D5DB',
    # Rating cell backgrounds (6)
    'rating_5_bg': '#FF0016',
    'rating_4_bg': '#FF8E1E',
    'rating_3_bg': '#FEFF2A',
    'rating_2_bg': '#4A86E8',
    'rating_1_bg': '#1800FB',
    'rating_0_bg': '#9200FC',
    # Rating text (6) — white on dark bgs (0-2), black on bright bgs (3-5)
    'rating_5_text': '#000000',
    'rating_4_text': '#000000',
    'rating_3_text': '#000000',
    'rating_2_text': '#FFFFFF',
    'rating_1_text': '#FFFFFF',
    'rating_0_text': '#FFFFFF',
    # Heat map anchors (3)
    'heatmap_high': '#FFB7FE',
    'heatmap_mid': '#FF8E1E',
    'heatmap_low': '#1800FB',
    # Completion heat map (3)
    'pct_high': '#FCB045',
    'pct_mid': '#B76D7D',
    'pct_low': '#833AB4',
    # Structural (6)
    'album_header_bg': '#F99FD0',
    'row_alternate': '#F7F9FD',
    'grid_line': '#333333',
    'header_user_bg': '#D9EAD3',
    # Artist navbar
    'artist_button_text': '#000000',
    # Top navbar active indicator
    'navbar_active': '#818CF8',
    # Search overlay section headers
    'search_section_bg': '#E5E7EB',
    'search_section_text': '#374151',
    # Unrated song count heat map (4)
    'unrated_0_bg': '#A4C2F4',
    'unrated_low_bg': '#B6D7A8',
    'unrated_mid_bg': '#FFE599',
    'unrated_high_bg': '#EA9999',
    'unrated_text': '#000000',
    # Action buttons
    'delete_button': '#DC2626',
    'edit_on_button': '#16a34a',
    'edit_off_button': '#6B7280',
    'button_text': '#FFFFFF',
    # Dropdown hover
    'hover_bg': '#808080',
    # Discography header
    'discography_background': '#000000',
    'discography_text': '#FFFFFF',
    # Duplicate song tag
    'duplicate_tag_bg': '#5B4A8A',
    'duplicate_tag_text': '#FFFFFF',
    # Update type badges
    'update_type_feature': '#2563EB',
    'update_type_bugfix': '#DC2626',
    'update_type_style': '#7C3AED',
    'update_type_perf': '#059669',
    'update_type_code': '#6B7280',
    # Submission type badges
    'submission_type_artist': '#7C3AED',
    'submission_type_album': '#2563EB',
    'submission_type_song': '#059669',
    'submission_type_rating': '#D97706',
    'submission_type_note': '#6B7280',
}

# Dark theme — all columns populated, no NULLs
DARK_THEME = {
    # UI chrome (17)
    'bg_primary': '#1A1A2E',
    'bg_secondary': '#16213E',
    'text_primary': '#E5E7EB',
    'text_secondary': '#9CA3AF',
    'navbar_bg': '#000000',
    'navbar_text': '#E5E7EB',
    'header_row': '#1E3A5F',
    'promoted_song': '#B05A7A',
    'gender_female': '#F472B6',
    'gender_male': '#60A5FA',
    'gender_mixed': '#00CC00',
    'gender_anime': '#FBBF24',
    'album_name': '#34D399',
    'link': '#60A5FA',
    'button_primary': '#3B82F6',
    'button_secondary': '#4B5563',
    'border': '#374151',
    # Rating cell backgrounds (6) — same as Classic (data semantics)
    'rating_5_bg': '#FF0016',
    'rating_4_bg': '#FF8E1E',
    'rating_3_bg': '#FEFF2A',
    'rating_2_bg': '#4A86E8',
    'rating_1_bg': '#1800FB',
    'rating_0_bg': '#9200FC',
    # Rating text (6) — white on dark bgs (0-2), black on bright bgs (3-5)
    'rating_5_text': '#000000',
    'rating_4_text': '#000000',
    'rating_3_text': '#000000',
    'rating_2_text': '#FFFFFF',
    'rating_1_text': '#FFFFFF',
    'rating_0_text': '#FFFFFF',
    # Heat map anchors (3)
    'heatmap_high': '#FFB7FE',
    'heatmap_mid': '#FF8E1E',
    'heatmap_low': '#1800FB',
    # Completion heat map (3)
    'pct_high': '#FCB045',
    'pct_mid': '#B76D7D',
    'pct_low': '#833AB4',
    # Structural (6) — dark variants
    'album_header_bg': '#B05A7A',
    'row_alternate': '#16213E',
    'grid_line': '#444444',
    'header_user_bg': '#1A3A2E',
    # Artist navbar
    'artist_button_text': '#000000',
    # Top navbar active indicator
    'navbar_active': '#818CF8',
    # Search overlay section headers
    'search_section_bg': '#374151',
    'search_section_text': '#9CA3AF',
    # Unrated song count heat map (4)
    'unrated_0_bg': '#A4C2F4',
    'unrated_low_bg': '#B6D7A8',
    'unrated_mid_bg': '#FFE599',
    'unrated_high_bg': '#EA9999',
    'unrated_text': '#000000',
    # Action buttons
    'delete_button': '#DC2626',
    'edit_on_button': '#16a34a',
    'edit_off_button': '#6B7280',
    'button_text': '#FFFFFF',
    # Dropdown hover
    'hover_bg': '#808080',
    # Discography header
    'discography_background': '#000000',
    'discography_text': '#FFFFFF',
    # Duplicate song tag
    'duplicate_tag_bg': '#5B4A8A',
    'duplicate_tag_text': '#FFFFFF',
    # Update type badges
    'update_type_feature': '#3B82F6',
    'update_type_bugfix': '#EF4444',
    'update_type_style': '#A78BFA',
    'update_type_perf': '#34D399',
    'update_type_code': '#9CA3AF',
    # Submission type badges
    'submission_type_artist': '#A78BFA',
    'submission_type_album': '#3B82F6',
    'submission_type_song': '#34D399',
    'submission_type_rating': '#FBBF24',
    'submission_type_note': '#9CA3AF',
}


def _validate_theme(theme_row, name):
    """Assert all colour columns are populated."""
    colour_cols = [c.name for c in Theme.__table__.columns
                   if c.name not in ('id', 'name', 'user_id')]
    for col in colour_cols:
        val = getattr(theme_row, col)
        if val is None:
            raise ValueError(f'{name} theme has NULL value for column: {col}')


def seed(db):
    """Create seed data. Idempotent — safe to re-run."""

    with db.session.no_autoflush:
        # 1. Lookup tables (no FK dependencies)
        for id_, name in [(0, 'Admin'), (1, 'Editor'), (2, 'User'), (3, 'Viewer'), (4, 'System')]:
            db.session.merge(Role(id=id_, role=name))

        for id_, name in [(0, 'Korean'), (1, 'Japanese'), (2, 'Canadian'), (3, 'American'), (4, 'Latin')]:
            db.session.merge(Country(id=id_, country=name))

        for id_, name in [(0, 'Kpop'), (1, 'Jpop'), (2, 'Pop'), (3, 'Rock'), (4, 'Metal'), (5, 'Vocaloid'), (7, 'VTuber')]:
            db.session.merge(Genre(id=id_, genre=name))

        for id_, type_, desc in [
            (0, 'Album', 'A normal album, typically longer than 30 minutes (~8+ songs)'),
            (1, 'EP', 'A short album, typically under 30 minutes (~3-7 songs)'),
            (2, 'Single', 'A single song released alone (sometimes with 1-2 accompanying songs)'),
        ]:
            db.session.merge(AlbumType(id=id_, type=type_, description=desc))

        for id_, name in [(0, 'Female'), (1, 'Male'), (2, 'Mixed'), (3, 'Anime')]:
            db.session.merge(GroupGender(id=id_, gender=name))

        for id_, name in [(0, 'Subunit'), (1, 'Soloist')]:
            db.session.merge(ArtistRelationship(id=id_, relationship=name))

        for id_, name in [(0, 'Song'), (1, 'Album'), (2, 'Artist'), (3, 'Legacy'), (4, 'Rating'), (5, 'Link')]:
            db.session.merge(ChangelogType(id=id_, type=name))

        for id_, type_, desc in [
            (1, 'Feature', 'New Feature'),
            (2, 'Bugfix', 'Bug Fix'),
            (3, 'Style', 'Themes And Layout Changes'),
            (4, 'Perf.', 'Performance Improvement'),
            (5, 'Code', 'Code-only changes, cleanup/refactors, no change for users'),
        ]:
            db.session.merge(UpdateType(id=id_, type=type_, description=desc))

        # Flush lookups so FK references resolve
        db.session.flush()

        # 2. Reserved Users
        db.session.merge(User(
            id=0, username='System', email=None, password=None,
            role_id=4, created_at=_now(), sort_order=None,
        ))
        db.session.merge(User(
            id=1, username='Guest', email=None, password=None,
            role_id=3, created_at=_now(), sort_order=None,
        ))
        existing_admin = db.session.get(User, 2)
        if existing_admin is None:
            db.session.add(User(
                id=2, username='Stealth', email='placeholder@arima.app',
                password=_hash('admin'), role_id=0, created_at=_now(), sort_order=1,
                profile_image='https://i.imgur.com/Nux0Yn7.png',
            ))

        # Flush users so theme FK resolves
        db.session.flush()

        # 3. Themes — Classic (id=0) and Dark (id=1)
        db.session.merge(Theme(id=0, name='Classic', user_id=None, **CLASSIC_THEME))
        db.session.merge(Theme(id=1, name='Dark', user_id=None, **DARK_THEME))
        db.session.flush()

        # Validate theme completeness
        _validate_theme(db.session.get(Theme, 0), 'Classic')
        _validate_theme(db.session.get(Theme, 1), 'Dark')

        # 4. Rules — single row (only create if missing, don't overwrite edits)
        if not db.session.get(Rules, 1):
            db.session.add(Rules(id=1, content='Rules have not been set yet.'))

        db.session.flush()

        # 5. Misc. Artists country subunits — rename, clean up, and sync
        misc = Artist.query.filter_by(name='Misc. Artists').first()
        if misc:
            # Remove orphan subunits (no songs) that don't match a country
            country_names = {c.country for c in Country.query.all()}
            all_children = Artist.query.join(
                ArtistArtist, ArtistArtist.artist_2 == Artist.id
            ).filter(ArtistArtist.artist_1 == misc.id).all()
            for child in all_children:
                # Check both short and legacy names
                short_name = child.name.replace('Misc. Artists - ', '')
                if short_name not in country_names and child.name not in country_names:
                    has_songs = ArtistSong.query.filter_by(artist_id=child.id).first()
                    if not has_songs:
                        Album.query.filter_by(artist_id=child.id).delete()
                        ArtistArtist.query.filter_by(artist_1=misc.id, artist_2=child.id).delete()
                        db.session.query(Artist).filter_by(id=child.id).delete()
                        print(f'  Removed empty subunit: {child.name}')

            db.session.flush()

            # Renames + creation handled by sync_misc_artist_stubs
            from app.services.artist import sync_misc_artist_stubs
            sync_misc_artist_stubs()

    # Fix AUTOINCREMENT sequences so new IDs start above reserved range.
    # sqlite_sequence is auto-created by SQLite on first AUTOINCREMENT insert.
    # Check if it exists before updating (it may not exist on first seed with merge).
    result = db.session.execute(db.text(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='sqlite_sequence'"
    )).fetchone()
    if result:
        for table, seq in [('user', 2), ('theme', 1)]:
            db.session.execute(db.text(
                "INSERT OR REPLACE INTO sqlite_sequence (name, seq) VALUES (:name, :seq)"
            ), {'name': table, 'seq': seq})

    db.session.commit()
