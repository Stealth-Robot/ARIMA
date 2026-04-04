from markupsafe import Markup, escape

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
    justification = db.Column(db.Text)

    user = db.relationship('User', foreign_keys=[user_id])
    artist = db.relationship('Artist')
    album = db.relationship('Album')
    song = db.relationship('Song')
    change_type = db.relationship('ChangelogType')

    @property
    def description_html(self):
        """Description with artist/song names linked to artist page."""
        desc = escape(self.description)
        if self.artist and self.artist.slug:
            artist_name = escape(self.artist.name)
            link = Markup('<a href="/artists/{}" style="color: var(--link);">{}</a>').format(
                self.artist.slug, self.artist.name)
            desc = desc.replace(f'"{artist_name}"', f'"{link}"')
        if self.song and self.artist and self.artist.slug and self.song.name != self.artist.name:
            song_name = escape(self.song.name)
            link = Markup('<a href="/artists/{}#song-{}" style="color: var(--link);">{}</a>').format(
                self.artist.slug, self.song.id, self.song.name)
            desc = desc.replace(f'"{song_name}"', f'"{link}"')
        return Markup(desc)

    __table_args__ = (
        db.Index('ix_changelog_artist_id', 'artist_id'),
        db.Index('ix_changelog_album_id', 'album_id'),
        db.Index('ix_changelog_song_id', 'song_id'),
        db.Index('ix_changelog_change_type_id', 'change_type_id'),
    )
