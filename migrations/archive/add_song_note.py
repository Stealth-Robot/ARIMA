"""Add note column to song table.

Run with: flask shell < migrations/add_song_note.py
"""

from app.extensions import db


def migrate():
    try:
        db.session.execute(db.text('ALTER TABLE song ADD COLUMN note TEXT'))
        print('Added note column to song.')
    except Exception as e:
        print(f'song.note column: {e}')

    db.session.commit()
    print('Migration complete: note added to song.')


migrate()
