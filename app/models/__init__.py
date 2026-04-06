# Import all models to ensure SQLAlchemy registers them
from app.models.lookups import Country, Genre, AlbumType, GroupGender, ArtistRelationship, UpdateType  # noqa: F401
from app.models.user import Role, User, UserSettings  # noqa: F401
from app.models.theme import Theme  # noqa: F401
from app.models.music import Artist, Song, Album, Rating, ArtistSong, AlbumSong, ArtistArtist, album_genres  # noqa: F401
from app.models.changelog import Changelog  # noqa: F401
from app.models.rules import Rules  # noqa: F401
from app.models.update import Update  # noqa: F401
