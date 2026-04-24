"""Add spotify_url column to album.

Run with: flask shell < migrations/add_album_spotify_url.py
"""

from app.extensions import db


def migrate():
    try:
        db.session.execute(db.text(
            "ALTER TABLE album ADD COLUMN spotify_url TEXT"
        ))
        print('Added spotify_url column to album.')
    except Exception as e:
        print(f'spotify_url: {e}')

    db.session.commit()
    print('Migration complete.')


migrate()
