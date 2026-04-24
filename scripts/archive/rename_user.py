"""One-time script to rename user id=6 to 'Emily'.

Usage:
    flask rename-user
"""

from app.extensions import db
from app.models.user import User


def rename_user():
    user = db.session.get(User, 6)
    if not user:
        print('User id=6 not found.')
        return
    old = user.username
    if old == 'Emily':
        print('User id=6 is already named Emily.')
        return
    user.username = 'Emily'
    db.session.commit()
    print(f'Renamed user id=6 from "{old}" to "Emily".')
