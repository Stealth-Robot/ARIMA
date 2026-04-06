"""Add hover_bg column to theme table.

Run with: flask shell < migrations/add_hover_bg.py
"""

from app.extensions import db


def migrate():
    # Add column
    try:
        db.session.execute(db.text('ALTER TABLE theme ADD COLUMN hover_bg TEXT'))
        print('Added hover_bg column.')
    except Exception as e:
        print(f'hover_bg column: {e}')

    # Set defaults on built-in themes — stored as hex, opacity applied in JS
    db.session.execute(
        db.text("UPDATE theme SET hover_bg = '#808080' WHERE id IN (0, 1) AND hover_bg IS NULL")
    )

    db.session.commit()
    print('Migration complete: hover_bg added to theme.')


migrate()
