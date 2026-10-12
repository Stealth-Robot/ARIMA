from app.extensions import db


class Changelog(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    date = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='SET NULL'))
    album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='SET NULL'))
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='SET NULL'))
    change_type_id = db.Column(db.Integer, db.ForeignKey('changelog_type.id'))
    description = db.Column(db.Text, nullable=False)
    description_html = db.Column(db.Text)
    search_description = db.Column(db.Text)
    justification = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id])
    artist = db.relationship('Artist')
    album = db.relationship('Album')
    song = db.relationship('Song')
    change_type = db.relationship('ChangelogType')

    __table_args__ = (
        db.Index('ix_changelog_artist_id', 'artist_id'),
        db.Index('ix_changelog_album_id', 'album_id'),
        db.Index('ix_changelog_song_id', 'song_id'),
        db.Index('ix_changelog_change_type_id', 'change_type_id'),
    )


def _sync_search_description(mapper, connection, target):
    from app.services.search import search_name_for
    target.search_description = search_name_for(target.description)


db.event.listen(Changelog, 'before_insert', _sync_search_description)
db.event.listen(Changelog, 'before_update', _sync_search_description)
