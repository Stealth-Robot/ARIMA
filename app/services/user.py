"""User management service — deletion with theme rename and sort_order compaction."""

from app.extensions import db
from app.models.user import User
from app.models.theme import Theme


def delete_user(user):
    """Delete a user with theme rename and sort_order compaction.

    Atomic — single commit:
    1. Rename personal theme to 'deleted_' + username
    2. Delete user (cascades to Ratings, UserSettings; SET NULL on others)
    3. Compact sort_order to close the gap
    """
    old_sort = user.sort_order
    username = user.username

    # 1. Rename personal theme
    personal_theme = Theme.query.filter_by(user_id=user.id).first()
    if personal_theme:
        personal_theme.name = f'deleted_{username}'

    # 2. Delete user
    db.session.delete(user)
    db.session.flush()

    # 3. Compact sort_order (SQLite doesn't support ORDER BY on UPDATE)
    if old_sort is not None:
        db.session.execute(
            db.text("""
                UPDATE user SET sort_order = sort_order - 1
                WHERE sort_order > :old_sort
            """),
            {'old_sort': old_sort}
        )

    db.session.commit()
