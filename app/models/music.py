from app.extensions import db


# Simple pivot — no extra columns
album_genres = db.Table(
    'album_genres',
    db.Column('album_id', db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id', ondelete='CASCADE'),
              primary_key=True),
)


class Artist(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    gender_id = db.Column(db.Integer, db.ForeignKey('group_gender.id'), nullable=False)
    country_id = db.Column(db.Integer, db.ForeignKey('country.id'), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    submission_id = db.Column(db.Integer, db.ForeignKey('submission.id', ondelete='RESTRICT'),
                              nullable=False)
    last_updated = db.Column(db.Text)
    is_disbanded = db.Column(db.Boolean, nullable=False, default=False)

    gender = db.relationship('GroupGender')
    country = db.relationship('Country')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    submission = db.relationship('Submission', foreign_keys=[submission_id])
    songs = db.relationship('Song', secondary='artist_song', back_populates='artists',
                            viewonly=True)
    children = db.relationship('ArtistArtist', foreign_keys='ArtistArtist.artist_1',
                               back_populates='parent')


class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    submission_id = db.Column(db.Integer, db.ForeignKey('submission.id', ondelete='RESTRICT'),
                              nullable=False)
    is_promoted = db.Column(db.Boolean, nullable=False, default=False)
    is_remix = db.Column(db.Boolean, nullable=False, default=False)

    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    submission = db.relationship('Submission', foreign_keys=[submission_id])
    artists = db.relationship('Artist', secondary='artist_song', back_populates='songs',
                              viewonly=True)
    albums = db.relationship('Album', secondary='album_song', back_populates='songs',
                             viewonly=True)
    ratings = db.relationship('Rating', back_populates='song', cascade='all, delete-orphan')


class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text, nullable=False)
    release_date = db.Column(db.Text, nullable=False)
    album_type_id = db.Column(db.Integer, db.ForeignKey('album_type.id'), nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    submission_id = db.Column(db.Integer, db.ForeignKey('submission.id', ondelete='RESTRICT'),
                              nullable=False)

    album_type = db.relationship('AlbumType')
    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    submission = db.relationship('Submission', foreign_keys=[submission_id])
    songs = db.relationship('Song', secondary='album_song', back_populates='albums',
                            viewonly=True)
    genres = db.relationship('Genre', secondary=album_genres, backref='albums')


class Rating(db.Model):
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text)

    song = db.relationship('Song', back_populates='ratings')
    user = db.relationship('User', back_populates='ratings')

    __table_args__ = (
        db.CheckConstraint('rating >= 0 AND rating <= 5', name='rating_range'),
    )


class ArtistSong(db.Model):
    __tablename__ = 'artist_song'
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                          primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    artist_is_main = db.Column(db.Boolean, nullable=False)


class AlbumSong(db.Model):
    __tablename__ = 'album_song'
    album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
                         primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    track_number = db.Column(db.Integer, nullable=False)

    __table_args__ = (
        db.UniqueConstraint('album_id', 'track_number', name='uq_album_track'),
    )


class ArtistArtist(db.Model):
    __tablename__ = 'artist_artist'
    artist_1 = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                         primary_key=True)
    artist_2 = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                         primary_key=True)
    relationship = db.Column(db.Integer, db.ForeignKey('artist_relationship.id'),
                             nullable=False)

    parent = db.relationship('Artist', foreign_keys=[artist_1], back_populates='children')
    child = db.relationship('Artist', foreign_keys=[artist_2])
    relationship_type = db.relationship('ArtistRelationship')
