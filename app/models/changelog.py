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
        desc = str(escape(self.description))
        if self.artist and self.artist.slug:
            artist_name = str(escape(self.artist.name))
            link = '<a href="/artists/{}" style="color: var(--link);">{}</a>'.format(
                escape(self.artist.slug), artist_name)
            desc = desc.replace('&#34;' + artist_name + '&#34;', '&#34;' + link + '&#34;')
            desc = desc.replace('&quot;' + artist_name + '&quot;', '&quot;' + link + '&quot;')
            desc = desc.replace('"' + artist_name + '"', '"' + link + '"')
        if self.song and self.artist and self.artist.slug and self.song.name != self.artist.name:
            song_name = str(escape(self.song.name))
            link = '<a href="/artists/{}#song-{}" style="color: var(--link);">{}</a>'.format(
                escape(self.artist.slug), self.song.id, song_name)
            desc = desc.replace('&#34;' + song_name + '&#34;', '&#34;' + link + '&#34;')
            desc = desc.replace('&quot;' + song_name + '&quot;', '&quot;' + link + '&quot;')
            desc = desc.replace('"' + song_name + '"', '"' + link + '"')
        return Markup(desc)

    __table_args__ = (
        db.Index('ix_changelog_artist_id', 'artist_id'),
        db.Index('ix_changelog_album_id', 'album_id'),
        db.Index('ix_changelog_song_id', 'song_id'),
        db.Index('ix_changelog_change_type_id', 'change_type_id'),
    )
