"""Add song_of_day table for Song of the Day feature.

Run with: flask shell < migrations/add_song_of_day.py
"""

from app.extensions import db


def migrate():
    try:
        db.session.execute(db.text(
            "CREATE TABLE IF NOT EXISTS song_of_day ("
            "  date TEXT PRIMARY KEY,"
            "  song_id INTEGER NOT NULL REFERENCES song(id) ON DELETE CASCADE"
            ")"
        ))
        db.session.execute(db.text(
            "CREATE INDEX IF NOT EXISTS ix_song_of_day_song_id ON song_of_day(song_id)"
        ))
        print('Created song_of_day table.')
    except Exception as e:
        print(f'song_of_day: {e}')

    db.session.commit()
    print('Migration complete.')


migrate()
