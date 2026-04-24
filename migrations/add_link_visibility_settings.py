"""Add link visibility columns to user_settings.

Run with: flask shell < migrations/add_link_visibility_settings.py
"""

from app.extensions import db


def migrate():
    for col in ('hide_autogen_youtube', 'hide_all_youtube', 'hide_all_spotify'):
        try:
            db.session.execute(db.text(
                f"ALTER TABLE user_settings ADD COLUMN {col} BOOLEAN NOT NULL DEFAULT 0"
            ))
            print(f'Added {col} column.')
        except Exception as e:
            print(f'{col}: {e}')

    db.session.commit()
    print('Migration complete.')


migrate()
