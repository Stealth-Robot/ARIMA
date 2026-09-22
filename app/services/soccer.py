from datetime import datetime, timedelta, timezone

# Row groups top to bottom: keeper last, being the least load-bearing for the squad.
# COUNT_LINES is a separate order and stays as the wireframe drew it.
CATEGORIES = ['guys', 'girls', 'keeper']
CATEGORY_LABELS = {'keeper': 'Keeper', 'guys': 'Guys', 'girls': 'Girls'}
COUNT_LINES = ['guys', 'girls', 'keeper', 'sum']

# Bounds on what one anonymous post can create, since every form here is public.
MAX_GAMES = 60          # days per season
MAX_NAME = 60           # season names, player names, kickoff labels
MAX_PLAYERS = 60        # per season
MAX_SEASONS = 60        # total
MAX_FUTURE_DAYS = 400   # how far ahead a day may be dated

# Thresholds are strict: a count equal to the number is NOT in that tier.
RED = {'keeper': 1, 'guys': 5, 'girls': 2, 'sum': 8}
YELLOW = {'guys': 6, 'girls': 3, 'sum': 10}

GREEN_BG, GREEN_FG = '#16A34A', '#FFFFFF'
YELLOW_BG, YELLOW_FG = '#FACC15', '#000000'
RED_BG, RED_FG = '#DC2626', '#FFFFFF'

AVAILABLE_BG, AVAILABLE_FG = '#16A34A', '#FFFFFF'
UNAVAILABLE_BG, UNAVAILABLE_FG = '#DC2626', '#FFFFFF'


def count_colour(kind, n):
    """(background, text) for one count line. Red wins, then yellow, else green."""
    if kind in RED and n < RED[kind]:
        return RED_BG, RED_FG
    if kind in YELLOW and n < YELLOW[kind]:
        return YELLOW_BG, YELLOW_FG
    return GREEN_BG, GREEN_FG


def cell_colour(row):
    """(background, text) for one availability cell; (None, None) when unset."""
    if row is None:
        return None, None
    return (AVAILABLE_BG, AVAILABLE_FG) if row.available else (UNAVAILABLE_BG, UNAVAILABLE_FG)


def season_counts(games, players, availability_map):
    """{game_id: {'guys': n, 'girls': n, 'keeper': n, 'sum': n}} of AVAILABLE players.

    Unset (no row) and explicitly unavailable both contribute zero.
    """
    category_of = {p.id: p.category for p in players}
    out = {}
    for game in games:
        counts = {'guys': 0, 'girls': 0, 'keeper': 0, 'sum': 0}
        for player_id, row in availability_map.get(game.id, {}).items():
            category = category_of.get(player_id)
            if row.available and category in counts:
                counts[category] += 1
        counts['sum'] = counts['guys'] + counts['girls'] + counts['keeper']
        out[game.id] = counts
    return out


def theme_color_scheme(theme):
    """'dark' or 'light' from the theme's own background.

    Native date/time pickers ignore CSS colours and follow color-scheme, so without this
    the popup and its indicator icon render light on a dark page.
    """
    raw = (theme or {}).get('bg_primary') or ''
    try:
        r, g, b = (int(raw.lstrip('#')[i:i + 2], 16) for i in (0, 2, 4))
    except (ValueError, TypeError):
        return 'light'
    return 'dark' if (0.299 * r + 0.587 * g + 0.114 * b) < 128 else 'light'


TIME_STEP_MIN = 5

# The kickoff picker is two selects, not a native time input: that is the only way to get
# exactly 5-minute steps and no am/pm field, both of which the native widget controls
# itself. Hours run 12, 1, 2 … 11 and mean noon through 11pm — an afternoon/evening clock,
# which is what "we play at 6" means for this fixture list.
HOUR_CHOICES = [(12, '12')] + [(h + 12, str(h)) for h in range(1, 12)]
MINUTE_CHOICES = [f'{m:02d}' for m in range(0, 60, TIME_STEP_MIN)]


def canonical_time(raw):
    """'HH:MM' snapped to the nearest 5 minutes; None for blank or unparseable input."""
    value = (raw or '').strip()
    if not value:
        return None
    try:
        t = datetime.strptime(value, '%H:%M')
    except (ValueError, TypeError):
        return None
    total = t.hour * 60 + int(round(t.minute / TIME_STEP_MIN) * TIME_STEP_MIN)
    total = min(total, 23 * 60 + 55)
    return f'{total // 60:02d}:{total % 60:02d}'


def time_from_form(form):
    """Read the two kickoff selects. Falls back to a plain 'kickoff' HH:MM field.

    Returns (value, present): `present` says the form carried the control at all, so an
    absent control leaves an existing time alone while a blank one clears it.
    """
    if 'kickoff_hour' in form or 'kickoff_minute' in form:
        hour = (form.get('kickoff_hour') or '').strip()
        minute = (form.get('kickoff_minute') or '').strip()
        if not hour:
            return None, True
        valid_hours = {str(v) for v, _ in HOUR_CHOICES}
        if hour not in valid_hours or minute not in MINUTE_CHOICES:
            return None, True
        return f'{int(hour):02d}:{minute}', True
    if 'kickoff' in form:
        return canonical_time(form['kickoff']), True
    return None, False


def canonical_date(raw):
    """'2026-9-8' -> '2026-09-08'; None if unparseable. Storage must be canonical or the
    TEXT date columns stop sorting chronologically."""
    try:
        return datetime.strptime((raw or '').strip(), '%Y-%m-%d').strftime('%Y-%m-%d')
    except (ValueError, TypeError):
        return None


def date_within_horizon(iso, days=MAX_FUTURE_DAYS):
    """Reject absurd dates from an unauthenticated form without rejecting real ones."""
    horizon = (datetime.now(timezone.utc).replace(tzinfo=None)
               + timedelta(days=days)).strftime('%Y-%m-%d')
    return iso <= horizon
