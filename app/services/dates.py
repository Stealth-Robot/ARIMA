import re
from datetime import datetime

_DATE_RE = re.compile(r'\d{4}-\d{2}-\d{2}')


def is_valid_release_date(value):
    """True if value is a real YYYY-MM-DD calendar date.

    Rejects malformed strings and impossible calendar dates (e.g. 2023-13-40,
    2021-02-30). An empty/None value is not a valid date.
    """
    if not value:
        return False
    if not _DATE_RE.fullmatch(value):
        return False
    try:
        datetime.strptime(value, '%Y-%m-%d')
    except ValueError:
        return False
    return True
