from app.extensions import db


# Simple pivot — no extra columns
album_genres = db.Table(
    'album_genres',
    db.Column('album_id', db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
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

    gender = db.relationship('GroupGender')
    country = db.relationship('Country')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    songs = db.relationship('Song', secondary=ArtistSong.__table__, back_populates='artists',
                            viewonly=True)
    children = db.relationship('ArtistArtist', foreign_keys='ArtistArtist.artist_1',
                               back_populates='parent')

    __table_args__ = (
        db.Index('ix_artist_country_id', 'country_id'),
    )


class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    is_promoted = db.Column(db.Boolean, nullable=False, default=False)
    is_remix = db.Column(db.Boolean, nullable=False, default=False)
    note = db.Column(db.Text)
    last_updated = db.Column(db.Text)
    spotify_url = db.Column(db.Text)
    youtube_url = db.Column(db.Text)

    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    artists = db.relationship('Artist', secondary=ArtistSong.__table__, back_populates='songs',
                              viewonly=True)
    albums = db.relationship('Album', secondary=AlbumSong.__table__, back_populates='songs',
                             viewonly=True)
    ratings = db.relationship('Rating', back_populates='song', cascade='all, delete-orphan')


class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    release_date = db.Column(db.Text, nullable=True)
    album_type_id = db.Column(db.Integer, db.ForeignKey('album_type.id'), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='SET NULL'), nullable=True)
    last_updated = db.Column(db.Text)

    album_type = db.relationship('AlbumType')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    artist = db.relationship('Artist', foreign_keys=[artist_id])
    songs = db.relationship('Song', secondary=AlbumSong.__table__, back_populates='albums',
                            viewonly=True)
    genres = db.relationship('Genre', secondary=album_genres, backref='albums')


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
