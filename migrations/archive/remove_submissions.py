"""One-time migration: remove submissions system.

Drops submission_id from artist, album, song, changelog tables.
Drops approved_by_id and submission_id from changelog.
Drops pending_item from theme.
Drops the submission table entirely.

Requires SQLite 3.35+ (DROP COLUMN support).
Run with: flask shell < migrations/remove_submissions.py
Or:       python -c "from app import create_app; app = create_app(); ctx = app.app_context(); ctx.push(); exec(open('migrations/remove_submissions.py').read())"
"""

from app.extensions import db


def migrate():
    db.session.execute(db.text('PRAGMA foreign_keys=OFF'))

    # 1. Drop submission_id from artist, album, song (set NULL first)
    for table in ('artist', 'album', 'song'):
        try:
            db.session.execute(db.text(f'ALTER TABLE {table} DROP COLUMN submission_id'))
        except Exception as e:
            print(f'  {table}.submission_id: {e}')

    # 2. Drop submission_id and approved_by_id from changelog
    for col in ('submission_id', 'approved_by_id'):
        try:
            db.session.execute(db.text(f'ALTER TABLE changelog DROP COLUMN {col}'))
        except Exception as e:
            print(f'  changelog.{col}: {e}')

    # 3. Drop pending_item from theme
    try:
        db.session.execute(db.text('ALTER TABLE theme DROP COLUMN pending_item'))
    except Exception as e:
        print(f'  theme.pending_item: {e}')

    # 4. Drop submission table
    db.session.execute(db.text('DROP TABLE IF EXISTS submission'))

    # 5. Clean up orphaned indexes
    for idx in ('ix_artist_submission_id', 'ix_album_submission_id',
                'ix_song_submission_id', 'ix_changelog_submission_id',
                'ix_submission_status'):
        try:
            db.session.execute(db.text(f'DROP INDEX IF EXISTS {idx}'))
        except Exception:
            pass

    # 6. Remove submission from sqlite_sequence
    try:
        db.session.execute(db.text("DELETE FROM sqlite_sequence WHERE name='submission'"))
    except Exception:
        pass

    db.session.execute(db.text('PRAGMA foreign_keys=ON'))
    db.session.commit()
    print('Migration complete: submissions system removed.')


migrate()
