"""Add stats_page_user table for per-user stats page display preferences.

Run with: flask shell < migrations/add_stats_page_user.py
"""

from app.extensions import db


def migrate():
    db.session.execute(db.text("""
        CREATE TABLE IF NOT EXISTS stats_page_user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            target_user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            visible BOOLEAN NOT NULL DEFAULT 1,
            sort_order INTEGER NOT NULL,
            UNIQUE(owner_id, target_user_id)
        )
    """))
    db.session.commit()
    print('Created stats_page_user table.')

    try:
        db.session.execute(db.text(
            "ALTER TABLE user_settings ADD COLUMN stats_users_mobile_only BOOLEAN NOT NULL DEFAULT 1"
        ))
        db.session.commit()
        print('Added stats_users_mobile_only column.')
    except Exception as e:
        print(f'stats_users_mobile_only: {e}')


migrate()
