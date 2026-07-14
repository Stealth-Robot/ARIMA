from app.extensions import db


# Simple pivot — no extra columns
album_genres = db.Table(
    'album_genres',
    db.Column('album_id', db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id', ondelete='CASCADE'),
              primary_key=True, index=True),
)

song_genres = db.Table(
    'song_genres',
    db.Column('song_id', db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id', ondelete='CASCADE'),
              primary_key=True, index=True),
)


# --- Association models (defined first so .__table__ is available for M2M secondary) ---

class ArtistSong(db.Model):
    __tablename__ = 'artist_song'
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                          primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    artist_is_main = db.Column(db.Boolean, nullable=False)

    __table_args__ = (
        db.Index('ix_artist_song_song_id', 'song_id'),
    )


class AlbumSong(db.Model):
    __tablename__ = 'album_song'
    album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
                         primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    track_number = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('album_id', 'track_number', name='uq_album_track'),
        db.Index('ix_album_song_song_id', 'song_id'),
    )


class ArtistArtist(db.Model):
    __tablename__ = 'artist_artist'
    artist_1 = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                         primary_key=True)
    artist_2 = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                         primary_key=True)
    relationship = db.Column(db.Integer, db.ForeignKey('artist_relationship.id'),
                             nullable=False)

    __table_args__ = (
        db.Index('ix_artist_artist_relationship', 'relationship'),
    )

    parent = db.relationship('Artist', foreign_keys=[artist_1], back_populates='children')
    child = db.relationship('Artist', foreign_keys=[artist_2])
    relationship_type = db.relationship('ArtistRelationship')


class ArtistSubscription(db.Model):
    __tablename__ = 'artist_subscription'
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        primary_key=True)
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                          primary_key=True)

    __table_args__ = (
        db.Index('ix_artist_subscription_artist_id', 'artist_id'),
    )


class SongMiscArtist(db.Model):
    __tablename__ = 'song_misc_artist'
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    misc_artist_id = db.Column(db.Integer, db.ForeignKey('misc_artist.id', ondelete='CASCADE'),
                               primary_key=True)
    artist_is_main = db.Column(db.Boolean, nullable=False)

    __table_args__ = (
        db.Index('ix_song_misc_artist_misc_artist_id', 'misc_artist_id'),
    )


# --- Entity models ---

class Artist(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=True, index=True)
    gender_id = db.Column(db.Integer, db.ForeignKey('group_gender.id'), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    last_updated = db.Column(db.Text)
    is_disbanded = db.Column(db.Boolean, nullable=False, default=False)
    is_complete = db.Column(db.Boolean, nullable=False, default=False)
    is_tracked = db.Column(db.Boolean, nullable=False, default=False)
    owner_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    maintainer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    spotify_url = db.Column(db.Text)
    image_url = db.Column(db.Text)

    gender = db.relationship('GroupGender')
    country = db.relationship('Country')
    owner = db.relationship('User', foreign_keys=[owner_id])
    maintainer = db.relationship('User', foreign_keys=[maintainer_id])
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    songs = db.relationship('Song', secondary=ArtistSong.__table__, back_populates='artists',
                            viewonly=True)
    children = db.relationship('ArtistArtist', foreign_keys='ArtistArtist.artist_1',
                               back_populates='parent')
    alt_names = db.relationship('ArtistAltName', back_populates='artist',
                                order_by='ArtistAltName.id',
                                cascade='all, delete-orphan')

    __table_args__ = (
        db.Index('ix_artist_country_id', 'country_id'),
    )


class ArtistAltName(db.Model):
    __tablename__ = 'artist_alt_name'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                          nullable=False)
    name = db.Column(db.Text, nullable=False)

    artist = db.relationship('Artist', back_populates='alt_names')

    __table_args__ = (
        db.Index('ix_artist_alt_name_artist_id', 'artist_id'),
    )


def resolve_display_name(main, ja=None, kr=None, zh=None, other=None, rom=None, en=None,
                         native=False, romanized=False, english=False,
                         nat_scope=(False, False, False, False),
                         en_scope=(False, False, False, False),
                         rom_scope=(False, False, False, False)):
    """Resolve the name to display from a song/album's aliases and a viewer's prefs.

    Model: a checked parent (native/romanized/english) is the DEFAULT mode for every
    song. A per-language override sub — nat/en/rom_scope indexed (ja, ko, zh, other) —
    says "for songs whose native name is this language, use this mode instead". A song
    with no native name always uses the default. Each language maps to at most one
    override mode (enforced in the UI). Missing alias for the chosen mode falls back to
    the default mode, then the main name.
    """
    native_name = ja or kr or zh or other  # native group is mutually exclusive
    lang_idx = 0 if ja else (1 if kr else (2 if zh else (3 if other else None)))

    modes = []
    if lang_idx is not None:
        if nat_scope[lang_idx]:
            modes.append('native')
        elif en_scope[lang_idx]:
            modes.append('english')
        elif rom_scope[lang_idx]:
            modes.append('romanized')
    default = 'native' if native else ('english' if english else ('romanized' if romanized else None))
    if default and default not in modes:
        modes.append(default)

    for m in modes:
        if m == 'native' and native_name:
            return native_name
        if m == 'english' and en:
            return en
        if m == 'romanized' and rom:
            return rom
    return main


class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    is_promoted = db.Column(db.Boolean, nullable=False, default=False)
    is_lead = db.Column(db.Boolean, nullable=False, default=False)
    is_remix = db.Column(db.Boolean, nullable=False, default=False)
    is_cover = db.Column(db.Boolean, nullable=False, default=False)
    note = db.Column(db.Text)
    last_updated = db.Column(db.Text)
    spotify_url = db.Column(db.Text)
    youtube_url = db.Column(db.Text)

    artists = db.relationship('Artist', secondary=ArtistSong.__table__, back_populates='songs',
                              viewonly=True)
    albums = db.relationship('Album', secondary=AlbumSong.__table__, back_populates='songs',
                             viewonly=True)
    ratings = db.relationship('Rating', back_populates='song', cascade='all, delete-orphan')
    genres = db.relationship('Genre', secondary=song_genres, backref='songs')
    misc_artists = db.relationship('MiscArtist', secondary=SongMiscArtist.__table__,
                                   back_populates='songs', viewonly=True)
    aliases = db.relationship('SongAlias', back_populates='song',
                              order_by='SongAlias.id', cascade='all, delete-orphan')

    def display_name(self, native=False, romanized=False, english=False,
                     nat_scope=(False, False, False, False),
                     en_scope=(False, False, False, False),
                     rom_scope=(False, False, False, False)):
        """Display title given a viewer's prefs. See resolve_display_name for the model."""
        ja = kr = zh = rom = en = other = None
        for a in self.aliases:
            if a.native_lang == 'ko':
                kr = a.name
            elif a.native_lang == 'ja':
                ja = a.name
            elif a.native_lang == 'zh':
                zh = a.name
            elif a.native_lang == 'rom':
                rom = a.name
            elif a.native_lang == 'en':
                en = a.name
            elif a.native_lang == 'other':
                other = a.name
        return resolve_display_name(self.name, ja=ja, kr=kr, zh=zh, other=other, rom=rom, en=en,
                                    native=native, romanized=romanized, english=english,
                                    nat_scope=nat_scope, en_scope=en_scope, rom_scope=rom_scope)


class SongAlias(db.Model):
    __tablename__ = 'song_alias'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        nullable=False)
    name = db.Column(db.Text, nullable=False)
    # NULL = plain searchable alias; 'ja' = native Japanese; 'ko' = native Korean;
    # 'zh' = native Chinese; 'rom' = romanized; 'en' = English; 'other' = native other.
    native_lang = db.Column(db.Text)

    song = db.relationship('Song', back_populates='aliases')

    __table_args__ = (
        db.Index('ix_song_alias_song_id', 'song_id'),
        # JP/KR/CN/Other are mutually exclusive: at most one of the group per song.
        db.Index('ux_song_alias_native_group', 'song_id', unique=True,
                 sqlite_where=db.text("native_lang IN ('ja', 'ko', 'zh', 'other')")),
        db.Index('ux_song_alias_native_rom', 'song_id', unique=True,
                 sqlite_where=db.text("native_lang = 'rom'")),
        db.Index('ux_song_alias_native_en', 'song_id', unique=True,
                 sqlite_where=db.text("native_lang = 'en'")),
    )


class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    release_date = db.Column(db.Text, nullable=True)
    album_type_id = db.Column(db.Integer, db.ForeignKey('album_type.id'), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='SET NULL'), nullable=True)
    note = db.Column(db.Text)
    last_updated = db.Column(db.Text)
    date_confirmed = db.Column(db.Boolean, nullable=False, default=False)
    spotify_url = db.Column(db.Text)

    album_type = db.relationship('AlbumType')
    artist = db.relationship('Artist', foreign_keys=[artist_id])
    songs = db.relationship('Song', secondary=AlbumSong.__table__, back_populates='albums',
                            viewonly=True)
    genres = db.relationship('Genre', secondary=album_genres, backref='albums')
    alt_names = db.relationship('AlbumAltName', back_populates='album',
                                order_by='AlbumAltName.id',
                                cascade='all, delete-orphan')

    def display_name(self, native=False, romanized=False, english=False,
                     nat_scope=(False, False, False, False),
                     en_scope=(False, False, False, False),
                     rom_scope=(False, False, False, False)):
        """Display title given a viewer's prefs. See resolve_display_name for the model."""
        ja = kr = zh = rom = en = other = None
        for a in self.alt_names:
            if a.native_lang == 'ko':
                kr = a.name
            elif a.native_lang == 'ja':
                ja = a.name
            elif a.native_lang == 'zh':
                zh = a.name
            elif a.native_lang == 'rom':
                rom = a.name
            elif a.native_lang == 'en':
                en = a.name
            elif a.native_lang == 'other':
                other = a.name
        return resolve_display_name(self.name, ja=ja, kr=kr, zh=zh, other=other, rom=rom, en=en,
                                    native=native, romanized=romanized, english=english,
                                    nat_scope=nat_scope, en_scope=en_scope, rom_scope=rom_scope)


class AlbumAltName(db.Model):
    __tablename__ = 'album_alt_name'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
                         nullable=False)
    name = db.Column(db.Text, nullable=False)
    # NULL = plain searchable alt name; 'ja' = native Japanese; 'ko' = native Korean;
    # 'zh' = native Chinese; 'rom' = romanized; 'en' = English; 'other' = native other.
    native_lang = db.Column(db.Text)

    album = db.relationship('Album', back_populates='alt_names')

    __table_args__ = (
        db.Index('ix_album_alt_name_album_id', 'album_id'),
        # JP/KR/CN/Other are mutually exclusive: at most one of the group per album.
        db.Index('ux_album_alt_name_native_group', 'album_id', unique=True,
                 sqlite_where=db.text("native_lang IN ('ja', 'ko', 'zh', 'other')")),
        db.Index('ux_album_alt_name_native_rom', 'album_id', unique=True,
                 sqlite_where=db.text("native_lang = 'rom'")),
        db.Index('ux_album_alt_name_native_en', 'album_id', unique=True,
                 sqlite_where=db.text("native_lang = 'en'")),
    )


class Rating(db.Model):
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        primary_key=True)
    rating = db.Column(db.Integer, nullable=True)
    note = db.Column(db.Text)

    song = db.relationship('Song', back_populates='ratings')
    user = db.relationship('User', back_populates='ratings')

    __table_args__ = (
        db.CheckConstraint('rating >= 0 AND rating <= 5', name='rating_range'),
        db.Index('ix_rating_user_id', 'user_id'),
    )


class MiscArtist(db.Model):
    __tablename__ = 'misc_artist'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False)

    country = db.relationship('Country')
    songs = db.relationship('Song', secondary=SongMiscArtist.__table__,
                            back_populates='misc_artists', viewonly=True)
    alt_names = db.relationship('MiscArtistAltName', back_populates='misc_artist',
                                order_by='MiscArtistAltName.id',
                                cascade='all, delete-orphan')


class MiscArtistAltName(db.Model):
    __tablename__ = 'misc_artist_alt_name'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    misc_artist_id = db.Column(db.Integer, db.ForeignKey('misc_artist.id', ondelete='CASCADE'),
                               nullable=False)
    name = db.Column(db.Text, nullable=False)

    misc_artist = db.relationship('MiscArtist', back_populates='alt_names')

    __table_args__ = (
        db.Index('ix_misc_artist_alt_name_misc_artist_id', 'misc_artist_id'),
    )
