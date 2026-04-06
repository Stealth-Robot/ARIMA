# ARIMA Technical Architecture

> Decisions and patterns for the developer. This document answers "how" — the whitepaper answers "what" and "why."

## 1. Project Structure

Flask app with blueprints for route modules.

```
ARIMA/
├── app/
│   ├── __init__.py          # create_app() factory
│   ├── config.py            # Config classes (Dev, Prod)
│   ├── extensions.py        # db, login_manager, bcrypt, csrf (shared instances)
│   ├── models/
│   │   ├── __init__.py      # import all models (ensures registration)
│   │   ├── user.py          # User, UserSettings, Role
│   │   ├── music.py         # Artist, Album, Song, Rating + pivot models
│   │   ├── theme.py         # Theme
│   │   ├── changelog.py     # Changelog
│   │   ├── update.py        # Update (daily activity log)
│   │   ├── rules.py         # Rules
│   │   └── lookups.py       # Country, Genre, AlbumType, GroupGender, ArtistRelationship
│   ├── routes/
│   │   ├── __init__.py      # register blueprints
│   │   ├── auth.py          # /login, /logout, /create-account, /guest
│   │   ├── home.py          # /
│   │   ├── artists.py       # /artists, /artists/<id> + HTMX fragments
│   │   ├── stats.py         # /artist-stats, /global-stats + HTMX fragments
│   │   ├── ratings.py       # /rate (POST)
│   │   ├── edit/            # Edit mode routes (artists, albums, songs)
│   │   ├── changelog.py     # /changelog
│   │   ├── rules.py         # /rules, /rules/edit
│   │   ├── views.py         # /views
│   │   ├── users.py         # /admin/users (User Management)
│   │   ├── admin.py         # /admin (database replacement, etc.)
│   │   ├── profile.py       # /profile, /profile/settings
│   │   ├── themes.py        # /themes, /themes/<id>/edit
│   │   ├── updates.py       # /updates (activity timeline)
│   │   ├── search.py        # /search
│   │   ├── events.py        # SSE events
│   │   └── health.py        # /health
│   ├── services/
│   │   ├── __init__.py
│   │   ├── stats.py         # Scored group calculation, averages, viewer-relative globals
│   │   ├── artist.py        # Artist operations
│   │   ├── audit.py         # Audit logging
│   │   ├── email.py         # Transactional email (Resend / SMTP)
│   │   ├── events.py        # Server-sent events
│   │   ├── user.py          # User deletion (theme rename → delete → compact sort_order)
│   │   └── theme.py         # Theme loading with Classic fallback
│   ├── templates/
│   │   ├── base.html        # Shell: <html>, navbar, theme CSS vars, HTMX/Tailwind CDN
│   │   ├── fragments/       # HTMX partials (no <html> wrapper)
│   │   │   ├── artist_discography.html
│   │   │   ├── rating_cell.html
│   │   │   ├── stats_row.html
│   │   │   └── ...
│   │   ├── auth/
│   │   │   └── login.html
│   │   └── *.html           # Full page templates
│   ├── static/
│   │   ├── css/
│   │   │   └── app.css      # Minimal custom CSS (Tailwind handles most)
│   │   ├── js/
│   │   │   ├── core.js      # Shared utilities
│   │   │   ├── edit.js      # Edit mode JS
│   │   │   └── ratings.js   # Rating interaction JS
│   │   └── img/             # Static assets (logo, default images)
│   ├── decorators.py        # @role_required, @admin_only, @editor_or_admin
│   └── seed.py              # Database seeding script
├── scripts/                 # Data import/export scripts
├── migrations/              # One-off schema migration scripts
├── kpop-rating-database-design.md
├── architecture.md
├── README.md
├── .gitignore
├── .env.example
├── requirements.txt
├── Procfile                 # Railway: web: gunicorn "app:create_app()"
└── runtime.txt              # python-3.12.x
```

### Why This Structure

- **`models/` split by domain** — not one giant `models.py`. Keeps imports clean and files under 200 lines each.
- **`services/`** — business logic that touches multiple models or requires transactions. Routes stay thin (validate input → call service → render template). This is not over-abstraction — these are the complex operations (user deletion, stats calculation) that would otherwise bloat route files.
- **`fragments/`** — HTMX partials live in their own directory so it's obvious which templates return full pages vs HTML chunks.
- **`extensions.py`** — avoids circular imports. Models import `db` from here; `create_app()` initialises it.

---

## 2. Dependencies

```
# requirements.txt
Flask==3.1.*
Flask-Login==0.6.*
Flask-Bcrypt==1.0.*
Flask-SQLAlchemy==3.1.*
Flask-WTF==1.2.*
Flask-Compress==1.*
gunicorn==23.*
python-dotenv==1.*
markdown==3.*
resend
```

- **No Alembic.** Schema migrations are handled as one-off scripts in `migrations/`. Alembic is worth adding if migrations become frequent.
- **Flask-WTF** provides CSRF protection.
- **Flask-Compress** for gzip response compression.
- **HTMX + Tailwind vendored locally** in `static/vendor/`. No npm, no build step, no bundler, no CDN dependency.

### Rebuilding Tailwind CSS

The app uses Tailwind CSS v2.2.19 (the last version that ships a pre-built CSS file with all utility classes). The vendored file is purged to ~9KB by removing unused classes. If you add new Tailwind classes to templates and they don't work, you need to rebuild from the full file.

**1. Download the full Tailwind CSS build:**

```bash
curl -o app/static/vendor/tailwind.min.css \
  https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css
```

This replaces the purged file with the complete ~3.7MB build containing all utility classes. The app will work immediately — new classes will now render correctly.

**2. Purge and re-minify:**

Once you've confirmed your new classes work, purge unused classes to shrink the file back down:

```bash
npm install -g purgecss
purgecss --config purgecss.config.js
```

This scans all templates and JS files (configured in `purgecss.config.js`), keeps only the classes actually used, and overwrites `tailwind.min.css` with the purged output.

**Important:** If you use Tailwind classes dynamically (e.g., built via string concatenation in JS or Jinja), PurgeCSS won't detect them. Add those classes to the `safelist` array in `purgecss.config.js` so they aren't stripped.

---

## 3. Database & SQLAlchemy Models

### Engine Configuration

```python
# config.py
import os

class Config:
    SECRET_KEY = os.environ['SECRET_KEY']
    PEPPER = os.environ['PEPPER']
    SQLALCHEMY_DATABASE_URI = 'sqlite:///arima.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = 2592000  # 30 days in seconds
```

SQLite with WAL mode enabled on connection (handles concurrent reads from the ~5 users):

```python
# extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_bcrypt import Bcrypt

db = SQLAlchemy()
login_manager = LoginManager()
bcrypt = Bcrypt()
```

The SQLite PRAGMAs must be registered inside `create_app()` after `db.init_app(app)`, because `db.engine` doesn't exist at import time (no app context yet):

```python
# __init__.py — inside create_app(), after db.init_app(app)
from sqlalchemy import event

with app.app_context():
    @event.listens_for(db.engine, "connect")
    def set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")  # SQLite has FKs OFF by default!
        cursor.close()
```

> **Critical:** SQLite foreign keys are OFF by default. The `PRAGMA foreign_keys=ON` must fire on every connection or all your ON DELETE CASCADE/SET NULL/RESTRICT rules are silently ignored.

### Model Conventions

- All models inherit from `db.Model`.
- Table names are lowercase snake_case (SQLAlchemy default).
- Lookup tables (Roles, Countries, etc.) use plain `Integer` PKs — no AUTOINCREMENT.
- Entity tables (Users, Artists, Songs, Albums, Changelog, Themes) use `autoincrement=True`.
- Timestamps as `Text` (not DateTime) to match SQLite's native text storage. Store as ISO 8601 strings.
- Boolean columns use `Boolean` type (SQLite stores as 0/1).

### Model Skeleton

Below is the shape of each model. The developer fills in the full column definitions from the whitepaper — this shows relationships, keys, and non-obvious patterns.

```python
# models/user.py
from flask_login import UserMixin

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    role = db.Column(db.Text, nullable=False, unique=True)

class User(UserMixin, db.Model):
    # UserMixin provides is_active, is_authenticated, is_anonymous, get_id()
    # get_id() returns str(self.id) by default — works with our integer PKs
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.Text, nullable=False, unique=True)
    email = db.Column(db.Text, unique=True)  # nullable
    password = db.Column(db.Text)             # nullable
    role_id = db.Column(db.Integer, db.ForeignKey('role.id'), nullable=False)
    sort_order = db.Column(db.Integer, unique=True)  # nullable
    # ... other columns per whitepaper

    role = db.relationship('Role')
    settings = db.relationship('UserSettings', uselist=False, back_populates='user',
                               cascade='all, delete-orphan')
    ratings = db.relationship('Rating', back_populates='user',
                              cascade='all, delete-orphan')

    # Role IDs: Admin=0, Editor=1, User=2, Viewer=3, System=4
    # Always check membership explicitly — never use < or > comparisons on role_id.

    @property
    def is_admin(self):
        return self.role_id == 0

    @property
    def is_editor_or_admin(self):
        return self.role_id in (0, 1)

    @property
    def can_rate(self):
        return self.role_id in (0, 1, 2)

    @property
    def is_system_or_guest(self):
        return self.email is None


class UserSettings(db.Model):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        primary_key=True)
    # ... columns per whitepaper
    user = db.relationship('User', back_populates='settings')
```

```python
# models/music.py
class Artist(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # ... other columns (name, gender_id, country_id, last_updated, is_disbanded)

    # Parent/child relationships
    children = db.relationship('ArtistArtist',
                               foreign_keys='ArtistArtist.artist_1',
                               back_populates='parent')

class Song(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # ... (name, is_promoted, is_remix, note)
    ratings = db.relationship('Rating', back_populates='song',
                              cascade='all, delete-orphan')

class Album(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # ... (name, release_date, album_type_id)
    genres = db.relationship('Genre', secondary='album_genres', back_populates='albums')

class Rating(db.Model):
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'),
                        primary_key=True)
    rating = db.Column(db.Integer, nullable=False)
    note = db.Column(db.Text)

    song = db.relationship('Song', back_populates='ratings')
    user = db.relationship('User', back_populates='ratings')

    __table_args__ = (
        db.CheckConstraint('rating >= 0 AND rating <= 5', name='rating_range'),
    )

# Pivot tables — use db.Table, not models (no extra columns beyond FKs)
# Exception: ArtistSong, AlbumSong, ArtistArtist need models because they have extra columns

class ArtistSong(db.Model):
    __tablename__ = 'artist_song'
    artist_id = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                          primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    artist_is_main = db.Column(db.Boolean, nullable=False)

class AlbumSong(db.Model):
    __tablename__ = 'album_song'
    album_id = db.Column(db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
                         primary_key=True)
    song_id = db.Column(db.Integer, db.ForeignKey('song.id', ondelete='CASCADE'),
                        primary_key=True)
    track_number = db.Column(db.Integer, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('album_id', 'track_number', name='uq_album_track'),
    )

class ArtistArtist(db.Model):
    __tablename__ = 'artist_artist'
    artist_1 = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                         primary_key=True)
    artist_2 = db.Column(db.Integer, db.ForeignKey('artist.id', ondelete='CASCADE'),
                         primary_key=True)
    relationship = db.Column(db.Integer,
                             db.ForeignKey('artist_relationship.id'), nullable=False)
    parent = db.relationship('Artist', foreign_keys=[artist_1])
    child = db.relationship('Artist', foreign_keys=[artist_2])

# Simple pivot — no extra columns, use db.Table
album_genres = db.Table('album_genres',
    db.Column('album_id', db.Integer, db.ForeignKey('album.id', ondelete='CASCADE'),
              primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id', ondelete='CASCADE'),
              primary_key=True),
)
```

### Seed Script Pattern

```python
# seed.py
def seed(db):
    """Run inside app context after db.create_all()."""
    from app.models import Role, User, Country, Genre, ...

    # 1. Lookup tables
    for id, name in [(0, 'Admin'), (1, 'Editor'), (2, 'User'), (3, 'Viewer'), (4, 'System')]:
        db.session.merge(Role(id=id, role=name))

    # 2. Reserved users, system themes
    # ... per whitepaper

    # 3. Fix AUTOINCREMENT sequences
    db.session.execute(db.text(
        "UPDATE sqlite_sequence SET seq = 2 WHERE name = 'user'"
    ))
    # ... repeat for each AUTOINCREMENT table

    db.session.commit()
```

Use `db.session.merge()` so the seed is idempotent — safe to re-run without duplicate errors.

---

## 4. Authentication & Session Architecture

### Flow

```
[Login Form] → POST /login
    → lookup User by username
    → bcrypt.check_password_hash(stored_hash, PEPPER + entered_password)
    → flask_login.login_user(user, remember=True)
    → redirect /

[Guest Button] → POST /guest
    → flask_login.login_user(guest_user, remember=True)
    → redirect /

[Create Account] → POST /create-account
    → validate email exists in Users (password IS NULL AND email IS NOT NULL)
    → validate username uniqueness
    → hash = bcrypt.generate_password_hash(PEPPER + password)
    → update User row, create UserSettings, create personal Theme
    → flask_login.login_user(user, remember=True)
    → redirect /

[Logout] → GET /logout
    → flask_login.logout_user()
    → session.clear()
    → redirect /login
```

### Logout

- `GET /logout` is protected by `@login_required`.
- Calls `logout_user()` to clear the Flask-Login session, then `session.clear()` to wipe all session data (including Guest filter preferences).
- Redirects to the login page.
- A "Logout" link is always visible in the navbar (far right, next to the username) on all pages that extend `base.html`.

### Key Decisions

- **Pepper handling:** The pepper is a `Config.PEPPER` value from the environment. It's prepended to the raw password *before* bcrypt hashing. This means changing the pepper invalidates all existing passwords — acceptable for v1 since the admin can re-invite users.
- **`@login_required`** on every route except `/login`, `/create-account`, `/guest`, and `/health`.
- **`login_manager.login_view = 'login'`** handles the redirect-to-login automatically.
- **Guest session:** Flask-Login logs in the Guest user object normally. The only difference is behavioural: routes check `current_user.is_system_or_guest` before writing to UserSettings and use session cookie storage instead.

### Role Checking Decorators

```python
# decorators.py
from functools import wraps
from flask import redirect, url_for
from flask_login import current_user

# Explicit role ID sets — never use < or > comparisons.
# If a new role is added, update these sets and the Roles lookup table.
ADMIN = {0}
EDITOR_OR_ADMIN = {0, 1}
USER_OR_ABOVE = {0, 1, 2}
ALL_ROLES = {0, 1, 2, 3}

def role_required(allowed_role_ids):
    """Allow only users whose role_id is in the given set.
    MUST be stacked below @login_required — this decorator only checks role,
    not authentication."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if current_user.role_id not in allowed_role_ids:
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated
    return decorator

# Usage — always stack with @login_required:
#
# @app.route('/admin/users')
# @login_required
# @role_required(ADMIN)
# def user_management(): ...
#
# @app.route('/rate', methods=['POST'])
# @login_required
# @role_required(USER_OR_ABOVE)
# def rate_song(): ...
#
# @login_required handles unauthenticated → redirect to login (with ?next=)
# @role_required handles insufficient role → redirect to home
```

Role checks use explicit ID sets — never numeric comparisons. If a role is added or IDs change, you update the sets in one place. The decorator takes a set, not a number, so every route is self-documenting about exactly which roles have access.

---

## 5. HTMX Fragment Strategy

### The Pattern

Every page has two response modes:

1. **Full page load** (normal GET) → returns the full template extending `base.html`
2. **HTMX request** (has `HX-Request` header) → returns just the fragment

```python
# Example: artists route
@app.route('/artists/<int:artist_id>')
@login_required
def artist_detail(artist_id):
    artist = Artist.query.get_or_404(artist_id)
    discography = get_discography(artist, current_user)

    if request.headers.get('HX-Request'):
        return render_template('fragments/artist_discography.html',
                               artist=artist, discography=discography)
    return render_template('artists.html',
                           artist=artist, discography=discography)
```

### Where HTMX Is Used

| Interaction | Trigger | Swap Target | Fragment |
|---|---|---|---|
| Select artist in bottom navbar | `hx-get="/artists/<id>"` | `#discography` | `artist_discography.html` |
| Rate a song | `hx-post="/rate"` | `#rating-<song_id>-<user_id>` (outerHTML) | `rating_cell.html` |
| Expand subunit row | `hx-get="/stats/subunit/<id>"` | next `<tr>` (afterend) | `stats_row.html` |
| Change country/genre filter | `hx-get` with query params | `#main-content` | page-specific fragment |
| Toggle remix on Artists page | `hx-post="/profile/settings"` + `hx-get` current page | `#discography` | `artist_discography.html` |
| Edit rules (inline) | `hx-get="/rules/edit"` | `#rules-content` | `rules_edit_form.html` |
| Save rules | `hx-post="/rules"` | `#rules-content` | `rules_display.html` |
| Search changelog | `hx-get="/changelog?q=..."` | `#changelog-list` | `changelog_list.html` |

### Conventions

- Full page templates live in `templates/`. They extend `base.html`.
- Fragments live in `templates/fragments/`. They do NOT extend `base.html` — they're bare HTML chunks.
- HTMX attributes go directly on HTML elements in templates. No JS configuration.
- Confirmation modals (for delete/reject) use `hx-confirm` for simple cases, or a server-rendered modal fragment for complex ones (listing affected rows).
- `hx-indicator` on the body or a spinner element for loading states.

### Sticky Headers

The Artist Stats and Global Stats pages need pinned/frozen headers. Use `position: sticky; top: 0;` on the `<thead>` with a `z-index` and theme-driven background colour. Pure CSS — no JS needed.

---

## 6. Theme Injection

### How It Works

On every page load, a Jinja2 context processor injects the user's resolved theme as CSS custom properties:

```python
# In create_app() or a separate theme.py service
@app.context_processor
def inject_theme():
    theme = get_resolved_theme(current_user)
    return {'theme': theme}
```

```python
# services/theme.py
def get_resolved_theme(user):
    """Return a dict of colour_name → hex_value with Classic fallback."""
    classic = Theme.query.get(0)

    if user.is_authenticated and not user.is_system_or_guest:
        selected_theme_id = user.settings.theme if user.settings else 0
        selected = Theme.query.get(selected_theme_id) or classic
    else:
        # Guest/anonymous: check session cookie, default to Classic
        selected_theme_id = session.get('theme', 0)
        selected = Theme.query.get(selected_theme_id) or classic

    # Build resolved dict: selected value if not None, else Classic value
    colour_columns = [c.name for c in Theme.__table__.columns
                      if c.name not in ('id', 'name', 'user_id')]
    resolved = {}
    for col in colour_columns:
        value = getattr(selected, col)
        resolved[col] = value if value is not None else getattr(classic, col)
    return resolved
```

```html
<!-- base.html -->
<style>
  :root {
    {% for name, value in theme.items() %}
    --{{ name | replace('_', '-') }}: {{ value }};
    {% endfor %}
  }
</style>
```

This turns `bg_primary: '#1a1a2e'` into `--bg-primary: #1a1a2e;`. Templates and Tailwind classes reference these:

```html
<nav class="bg-[var(--navbar-bg)] text-[var(--navbar-text)]">
```

### Guest Theme Handling

Guest preferences (including theme) are stored in the Flask session cookie only. The `inject_theme` context processor reads `session.get('theme', 0)` for guests. When the session expires, it defaults back to Classic.

> **Performance note:** `get_resolved_theme` runs 2 DB queries per page load (Classic theme + selected theme). At ~5 users this is negligible. If it ever matters, this is the first candidate for per-request caching (e.g., `g.resolved_theme`).

---

## 7. Global Filters (Country/Genre)

### State Management

The selected country and genre live in:
- **UserSettings** for logged-in users (persisted to DB)
- **Session cookie** for Guest

### Approach

A Jinja2 context processor loads the current filters on every request:

```python
@app.context_processor
def inject_filters():
    if current_user.is_authenticated and not current_user.is_system_or_guest:
        settings = current_user.settings
        country_id = settings.country if settings else None
        genre_id = settings.genre if settings else None
    else:
        country_id = session.get('country')
        genre_id = session.get('genre')

    return {
        'current_country': country_id,  # None = "All"
        'current_genre': genre_id,       # None = "All"
        'countries': Country.query.all(),
        'genres': Genre.query.all(),
    }
```

Changing a filter sends an `hx-post` to `/profile/settings` (which updates UserSettings or session) and then re-fetches the current page content via `hx-get`.

### Query Filtering Pattern

Routes that respect the genre filter use a helper:

```python
def apply_genre_filter(query, genre_id):
    """Filter a Song/Album query by genre. None = no filter."""
    if genre_id is None:
        return query
    return query.join(AlbumSong).join(Album).join(album_genres).filter(
        album_genres.c.genre_id == genre_id
    )
```

---

## 8. Stats Calculation Strategy

### Viewer-Relative Globals

Global averages are NOT precomputed. They are calculated per-request, relative to the viewing user's settings (`include_featured`, `include_remixes`). This means:

1. Determine the viewing user's song set (exclude featured/remixes per settings).
2. For each artist, compute the average across all users who rated at least one song.
3. Exclude users with zero ratings from the denominator.

This is acceptable at ~5 users and hundreds of artists. The queries hit SQLite, which keeps the entire DB in memory for a file this small. No caching layer needed.

### Scored Group Count

Computed live per the whitepaper rules. The 80% threshold is a constant in `services/stats.py`:

```python
SCORED_GROUP_THRESHOLD = 0.80  # hardcoded per whitepaper
```

### Subunit Song Aggregation

When calculating parent artist stats, application code:
1. Queries `ArtistArtist` for children where `relationship = 0` (Subunit).
2. Unions subunit songs into the parent's song set.
3. Does NOT union soloist songs (relationship = 1) — soloists are standalone.

This runs per stats page load. No materialised views, no pre-aggregation.

---

## 9. User Deletion Transaction

Another multi-step operation that must be atomic:

```python
# services/user.py
def delete_user(user):
    """Delete user with theme rename and sort_order compaction."""
    old_sort = user.sort_order

    # 1. Rename personal theme
    personal_theme = Theme.query.filter_by(user_id=user.id).first()
    if personal_theme:
        personal_theme.name = f'deleted_{user.username}'

    # 2. Delete user (cascades to Ratings, UserSettings; SET NULL on others)
    db.session.delete(user)
    db.session.flush()  # execute DELETE before compacting

    # 3. Compact sort_order
    if old_sort is not None:
        db.session.execute(
            db.text("""
                UPDATE user SET sort_order = sort_order - 1
                WHERE sort_order > :old_sort
                ORDER BY sort_order ASC
            """),
            {'old_sort': old_sort}
        )

    db.session.commit()
```

---

## 10. Deployment (Railway)

### Procfile

```
web: gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1
```

> **Why `--workers 1`:** SQLite doesn't handle concurrent writers from multiple processes. A single gunicorn worker avoids write-lock contention. This is fine for ~5 users. If you ever need more throughput, switch to Postgres first, then increase workers.

### Environment Variables

```
SECRET_KEY=<random 64-char hex>
PEPPER=<random 32-char hex>
```

### Persistent Volume

Railway persistent volume mounted at `/data`. The SQLite database lives at `/data/arima.db`. In production config:

```python
class ProdConfig(Config):
    SQLALCHEMY_DATABASE_URI = 'sqlite:////data/arima.db'
```

### Flask CLI Seed Command

Register a CLI command in `create_app()` so seeding is repeatable and version-controlled:

```python
# __init__.py — inside create_app()
@app.cli.command('seed')
def seed_command():
    """Create all tables and insert seed data."""
    db.create_all()
    from app.seed import seed
    seed(db)
    click.echo('Database seeded.')
```

### First Deploy

1. Push to GitHub → Railway auto-deploys.
2. SSH/exec into the container: `flask seed`.
3. Done. Subsequent deploys are just code pushes. Re-running `flask seed` is safe (idempotent via `db.session.merge`).

---

## 11. Decisions That Can Wait

These are explicitly NOT decided now. Defer until the developer hits them:

| Decision | When to Decide |
|---|---|
| Alembic/migrations tooling | If migrations become frequent enough to warrant it |
| Caching layer (Redis, etc.) | If page loads become noticeably slow (unlikely at ~5 users) |
| Rate limiting | If abuse is observed (unlikely in a trusted friend group) |

---

## 12. Implementation Order

Recommended sequence (matches issue numbers):

```
Phase 1: Foundation
  #1  Project Setup
  #2  Database Schema & Seed
  #3  Authentication
  #5  Permissions (RBAC)
  #6  Theme System

Phase 2: Core Loop
  #4  Login Page
  #7  Navbar & Filters
  #8  Home Page
  #12 Rating System

Phase 3: Main Pages
  #21 Subunit/Soloist Logic (needed before stats/artists)
  #9  Artists Page
  #10 Artist Stats
  #11 Global Stats

Phase 4: Content & Admin
  #15 Changelog
  #16 Rules Page
  #17 Views Page
  #18 User Management
  #19 Profile Page
  #20 Themes Page
```

Phase 1 is pure backend — no UI needed to validate. Phase 2 gets a working login-to-homepage flow. Phase 3 is the meat of the app. Phase 4 is admin tooling and content management.

---

## 13. Rating Colours & Heat Maps

### Decision: ALL colours go in the Theme table.

Per the whitepaper: **"Every colour used in the app is a column in this table. No hardcoded colours — all colours are theme-driven."** This includes rating cell colours, heat map anchors, and structural colours. Users with personal themes can customise every visual aspect.

### New Theme Columns Required

Add the following columns to the Themes table (all `Text`, nullable, Classic fallback as with all other theme columns):

**Rating cell backgrounds (6 columns):**

| Column | Classic | Dark | Purpose |
|--------|---------|------|---------|
| `rating_5_bg` | `#FF0016` | `#FF0016` | Score 5 cell (Red) |
| `rating_4_bg` | `#FF8E1E` | `#FF8E1E` | Score 4 cell (Orange) |
| `rating_3_bg` | `#FEFF2A` | `#FEFF2A` | Score 3 cell (Yellow) |
| `rating_2_bg` | `#9EFFA4` | `#9EFFA4` | Score 2 cell (Light Green) |
| `rating_1_bg` | `#8AB5FC` | `#8AB5FC` | Score 1 cell (Light Blue) |
| `rating_0_bg` | `#9200FC` | `#9200FC` | Score 0 cell (Purple) |

**Rating text colours (2 columns):**

| Column | Classic | Dark | Purpose |
|--------|---------|------|---------|
| `rating_text_light` | `#FFFFFF` | `#FFFFFF` | Text on dark cells (scores 0, 5) |
| `rating_text_dark` | `#000000` | `#000000` | Text on light cells (scores 1-4) |

**Heat map anchors — average scores (3 columns):**

| Column | Classic | Dark | Purpose |
|--------|---------|------|---------|
| `heatmap_high` | `#FFB7FE` | `#FFB7FE` | Avg 4-5 (Pink) |
| `heatmap_mid` | `#FF8E1E` | `#FF8E1E` | Avg 2.5-4 (Orange) |
| `heatmap_low` | `#8AB5FC` | `#8AB5FC` | Avg 0-2.5 (Blue) |

**Completion heat map anchors — percentages (3 columns):**

| Column | Classic | Dark | Purpose |
|--------|---------|------|---------|
| `pct_high` | `#FFB7FE` | `#FFB7FE` | 80-100% (Pink) |
| `pct_mid` | `#FCA644` | `#FCA644` | 40-79% (Orange) |
| `pct_low` | `#8AB5FC` | `#8AB5FC` | 1-39% (Blue) |

**Structural colours (5 columns):**

| Column | Classic | Dark | Purpose |
|--------|---------|------|---------|
| `album_header_bg` | `#E6EBF4` | `#1E3A5F` | Album header row on artist page |
| `row_alternate` | `#F7F9FD` | `#16213E` | Alternating row background |
| `grid_line` | `#C0C0C0` | `#374151` | Cell borders |
| `key_bg_standard` | `#FF8E1E` | `#FF8E1E` | Key column bg (Standard) |
| `key_bg_stealth` | `#FEFF2A` | `#FEFF2A` | Key column bg (Stealth) |

**Total: 19 new columns.** Combined with existing 17, the Themes table will have 36 colour columns. This is the column-per-colour approach working as designed.

### Heat Map Interpolation

For continuous values (averages, percentages), interpolate between the theme's anchor colours using linear RGB interpolation. Implement as a helper in `services/theme.py`:

```python
def score_to_colour(value, theme):
    """Interpolate heat map colour for an average score (0-5)."""
    # Uses theme['heatmap_high'], theme['heatmap_mid'], theme['heatmap_low']
    # Returns hex string
```

### Rating Key Labels

These are **not colours** — they are text content. Store as application constants (not in Theme table):

```python
# app/constants.py
RATING_KEY_STANDARD = {
    5: 'Fucking banger', 4: 'Great song', 3: 'A vibe',
    2: 'Eh / Mid / No opinion', 1: "This isn't great", 0: 'Absolute shit',
}
RATING_KEY_STEALTH = {
    5: 'Fucking banger', 4: 'Bit of a Bop', 3: 'Decent/Lacking Pop',
    2: 'Mid / kinda bad', 1: 'Bad', 0: 'I feel Offended',
}
```

The Key column cycles: Standard (7 rows: header + 6 scores) → Stealth (7 rows) → repeat.

---

## 14. UI Refinement Plan (Issues #36–#47)

### Grouping and Dependencies

The 12 open issues fall into 4 work batches. Each batch can be done as a single commit or a small set of commits.

#### Batch A: Data Pipeline Fix (must run first — re-import required)
**Issues: #38 (gender extraction), #45 (user merge)**

These change the data in the database. Everything else is visual — do this batch first, re-import once, then all visual work operates on correct data.

**#38 — Gender extraction:**
- Update `scripts/export_spreadsheet.py` to read `ws.sheet_properties.tabColor.rgb`
- Colour mapping: `FFFF00FF` → female, `FF4A86E8`/`FF3C78D8` → male, `FF00FF00` → mixed, default → mixed
- Add `"gender"` field to each artist entry in JSON output
- Subunits/soloists inherit parent's tab colour
- Update `scripts/import_data.py` to read `gender` field and set `gender_id` accordingly
- **Must open workbook without `data_only=True`** to read tab colours (or open twice)

**#45 — User merge:**
- One-time migration: create `flask merge-users` CLI command
- Transfer ratings: `UPDATE rating SET user_id = 2 WHERE user_id = 4`
- Transfer sort_order: copy Stealth's sort_order to Stealth (admin)
- Delete Stealth user (id=4) — cascades UserSettings
- Run after import, before any visual work

**After Batch A:** Delete DB, re-run `flask seed && flask import-data data.json`, then `flask merge-users`.

#### Batch B: Theme + CSS Fixes (no backend changes, pure visual)
**Issues: #41 (album colour), #42 (top navbar), #47 (cell borders), #36 (bottom navbar scroll)**

All are theme seed updates or CSS changes. Can be done in one commit.

**#41 — Album header colour:**
- Update Classic seed: `album_header_bg = '#F99FD0'`
- Update Dark seed: `album_header_bg = '#5C2A4A'` (dark pink variant)

**#42 — Top navbar:**
- Update Classic seed: `navbar_bg = '#000000'`
- In `base.html`: add `flex-nowrap` to nav, increase `gap-4` to `gap-6`
- Ensure all nav items stay on one line

**#47 — Cell borders:**
- In `app.css`: change grid line from `var(--grid-line)` to `1px solid #000` on all table cells
- Or update Classic seed: `grid_line = '#000000'` (simpler — uses existing theme var)
- Verify `border-collapse: collapse` eliminates gaps

**#36 — Bottom navbar scroll:**
- Add `height: 36px` and `overflow-y: hidden` to bottom nav container
- Verify `whitespace-nowrap` and `overflow-x-auto` are working

#### Batch C: Template Fixes (logic changes in Jinja2 templates)
**Issues: #37 (navbar gender bg), #40 (key column cycle), #43 (heatmap steps), #44 (remove stats col 3), #46 (admin nav link)**

**#37 — Bottom navbar gender bg:**
- Change from `color: var(--gender-X)` to `background-color: var(--gender-X); color: white`
- Artist name text becomes white on coloured background
- Active artist: add a border or underline for distinction

**#40 — Key column 14-row cycle:**
The current implementation has a bug — the cycle counter doesn't properly do the 14-row pattern. Fix:
```
Row 0: "Key (Standard)" header
Row 1-6: Standard scores 5,4,3,2,1,0
Row 7: "Key (Stealth Ver)" header
Row 8-13: Stealth scores 5,4,3,2,1,0
Row 14: back to "Key (Standard)" (row 0)
```
The cycle position should be `key_cycle % 14`. Position 0 and 7 are headers, 1-6 are Standard scores, 8-13 are Stealth scores.

**#43 — Heatmap step-based colours:**
Replace `score_to_colour()` linear interpolation with step-based matching:

```python
# STATS page (average scores) — step-based, not gradient
def score_to_colour(value, theme):
    if value is None or value == 0: return '#FFFFFF'
    if value >= 5.0: return theme.get('rating_5_bg', '#FF0016')  # Red
    if value >= 4.5: return theme.get('heatmap_high', '#FFB7FE')  # Pink
    if value >= 3.5: return theme.get('rating_4_bg', '#FF8E1E')  # Orange
    if value >= 2.5: return theme.get('rating_3_bg', '#FEFF2A')  # Yellow
    if value >= 1.5: return theme.get('rating_2_bg', '#9EFFA4')  # Green
    return theme.get('rating_1_bg', '#8AB5FC')  # Blue
```

For STATS 2.0 (percentages), use a purple→orange gradient:
- Update theme seeds: `pct_high = '#FCB045'` (orange/gold), `pct_low = '#833AB4'` (purple)
- Linear interpolation between purple (0%) and orange (100%)

**#44 — Remove third column group:**
- Delete Set 3 (rated count) columns from `artist_stats.html` and `fragments/stats_row.html`
- Remove the separator column before Set 3
- Keep Set 1 (% rated), Song Count, Set 2 (unrated count)

**#46 — Admin nav link:**
- Add to `base.html` navbar: `{% if current_user.is_admin %}<a href="/admin/users">Users</a>{% endif %}`

#### Batch D: Rating Interaction (standalone JS work)
**Issue: #39 (inline input with Enter/Escape/auto-advance)**

This is the biggest single change and is completely independent of everything else. It replaces the popover JS in `app.js`.

**Design:**
- Click cell → replace cell content with `<input type="text" maxlength="1" inputmode="numeric">`
- Input auto-focuses and selects existing value
- `keydown` handler:
  - Enter: validate 0-5, POST via `htmx.ajax()`, find next cell below (same column, next `<tr>`), trigger click on it
  - Escape: remove input, restore original content
  - Any other key that's not 0-5: ignore
- `blur` event: same as Escape (cancel)
- After HTMX response replaces the cell, the new cell will have `onclick` ready for the next interaction
- "Next cell below" logic: walk DOM from current `<td>` → parent `<tr>` → `nextElementSibling` → find `<td>` at same column index

### Implementation Order

```
Batch A: #38 + #45 → re-import data
Batch B: #41 + #42 + #47 + #36 → theme/CSS (one commit)
Batch C: #37 + #40 + #43 + #44 + #46 → template fixes (one or two commits)
Batch D: #39 → rating interaction (standalone commit)
```

Total: 4 batches, ~4 commits. Each batch is independently testable.
