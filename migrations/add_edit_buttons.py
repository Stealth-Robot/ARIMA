"""Add edit_buttons JSON column to user_settings.

Run with: flask shell < migrations/add_edit_buttons.py
"""

from app.extensions import db


def migrate():
    try:
        db.session.execute(db.text(
            "ALTER TABLE user_settings ADD COLUMN edit_buttons JSON NOT NULL DEFAULT '[]'"
        ))
        print('Added edit_buttons column.')
    except Exception as e:
        print(f'edit_buttons: {e}')

    db.session.execute(db.text(
        """UPDATE user_settings SET edit_buttons = '["__all__"]' WHERE edit_buttons = '[]'"""
    ))
    db.session.commit()
    print('Migration complete.')


migrate()
