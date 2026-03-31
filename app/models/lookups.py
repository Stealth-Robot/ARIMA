from app.extensions import db


class Country(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    country = db.Column(db.Text, nullable=False, unique=True)


class Genre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    genre = db.Column(db.Text, nullable=False, unique=True)


class AlbumType(db.Model):
    __tablename__ = 'album_type'
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.Text, nullable=False, unique=True)
    description = db.Column(db.Text)


class GroupGender(db.Model):
    __tablename__ = 'group_gender'
    id = db.Column(db.Integer, primary_key=True)
    gender = db.Column(db.Text, nullable=False, unique=True)


class ArtistRelationship(db.Model):
    __tablename__ = 'artist_relationship'
    id = db.Column(db.Integer, primary_key=True)
    relationship = db.Column(db.Text, nullable=False, unique=True)
