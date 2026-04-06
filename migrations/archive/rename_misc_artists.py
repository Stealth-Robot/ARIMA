"""One-time migration: shorten Misc. Artists subunit and album names.

Renames:
  - Subunit artists: "Misc. Artists - Korean" -> "Korean"
  - Genre albums:    "Misc. Artists - Kpop"   -> "Kpop"

Run with: flask shell < migrations/rename_misc_artists.py
Or:       python -c "from app import create_app; app = create_app(); ctx = app.app_context(); ctx.push(); exec(open('migrations/rename_misc_artists.py').read())"
"""

from app.extensions import db
from app.models.music import Artist, Album, ArtistArtist
from app.services.artist import generate_unique_slug


PREFIX = 'Misc. Artists - '


def migrate():
    misc = Artist.query.filter_by(name='Misc. Artists').first()
    if not misc:
        print('Misc. Artists not found — skipping')
        return

    # Rename subunit artists
    children = Artist.query.join(
        ArtistArtist, ArtistArtist.artist_2 == Artist.id
    ).filter(ArtistArtist.artist_1 == misc.id).all()

    existing_slugs = {a.slug for a in Artist.query.all() if a.slug}
    for child in children:
        if child.name.startswith(PREFIX):
            short_name = child.name[len(PREFIX):]
            print(f'  Artist: "{child.name}" -> "{short_name}"')
            existing_slugs.discard(child.slug)
            child.name = short_name
            child.slug = generate_unique_slug(short_name, existing_slugs)
            existing_slugs.add(child.slug)

    # Rename genre albums (catch both "Misc. Artists - X" and "Misc Artists - X")
    legacy_albums = Album.query.filter(
        db.or_(
            Album.name.like(f'{PREFIX}%'),
            Album.name.like('Misc Artists - %'),
        )
    ).all()
    for album in legacy_albums:
        dash_pos = album.name.index(' - ')
        short_name = album.name[dash_pos + 3:]
        print(f'  Album: "{album.name}" -> "{short_name}"')
        album.name = short_name

    db.session.commit()
    print(f'Done — renamed {len(children)} subunits and their albums.')


migrate()
