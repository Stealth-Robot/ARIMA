"""Add not_variant table for dismissed variant songs.

Run with: flask shell < migrations/add_not_variant.py
"""

from app.extensions import db


def migrate():
    try:
        db.session.execute(db.text(
            "CREATE TABLE IF NOT EXISTS not_variant ("
            "  song_id INTEGER PRIMARY KEY REFERENCES song(id) ON DELETE CASCADE"
            ")"
        ))
        print('Created not_variant table.')
    except Exception as e:
        print(f'not_variant: {e}')

    db.session.commit()
    print('Migration complete.')


migrate()
