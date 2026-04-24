# ARIMA Technical Architecture

> Non-obvious decisions and patterns. If it's readable from the code, it doesn't belong here.

## 1. Project Structure

- **`models/` split by domain** — not one giant `models.py`. Keeps imports clean and files under 200 lines each.
- **`services/`** — business logic that touches multiple models or requires transactions. Routes stay thin (validate input → call service → render template).
- **`templates/fragments/`** — HTMX partials live in their own directory so it's obvious which templates return full pages vs HTML chunks.
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

The app uses Tailwind CSS v2.2.19 (the last version that ships a pre-built CSS file with all utility classes). Tailwind v3+ and v4 require an npm-based build step to generate CSS, which is not an option for this project due to security restrictions on npm for web-deployed applications. The vendored file is purged to ~9KB by removing unused classes. If you add new Tailwind classes to templates and they don't work, you need to rebuild from the full file.

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

## 3. Database

### SQLite Configuration

- **WAL mode** and **foreign keys ON** are set via SQLAlchemy event listener on every connection (in `create_app()`).
- **Critical:** SQLite foreign keys are OFF by default. Without the `PRAGMA foreign_keys=ON`, all ON DELETE CASCADE/SET NULL rules are silently ignored.
- **Single gunicorn worker** in production — SQLite doesn't handle concurrent writers from multiple processes.

---

## 4. Authentication

### Key Decisions

- **Pepper handling:** The pepper (`PEPPER` env var) is prepended to the raw password *before* bcrypt hashing. Changing the pepper invalidates all existing passwords.
- **`@login_required`** on every route except `/login`, `/create-account`, `/guest`, and `/health`.
- **Guest session:** Flask-Login logs in the Guest user object normally. Routes check `current_user.is_system_or_guest` before writing to UserSettings and use session cookie storage instead.
- **Role checks use explicit ID sets** — never numeric comparisons (`role_id < 2`). If a role is added, update the sets in `decorators.py`.

---

## 5. HTMX Fragment Strategy

Every page has two response modes:

1. **Full page load** (normal GET) → returns the full template extending `base.html`
2. **HTMX request** (has `HX-Request` header) → returns just the fragment

| Interaction | Trigger | Fragment |
|---|---|---|
| Select artist in bottom navbar | `hx-get="/artists/<id>"` | `artist_discography.html` |
| Rate a song | `hx-post="/rate"` | `rating_cell.html` |
| Expand subunit row | `hx-get="/stats/subunit/<id>"` | `stats_row.html` |
| Change country/genre filter | `hx-get` with query params | page-specific fragment |
| Edit rules (inline) | `hx-get="/rules/edit"` | `rules_edit_form.html` |
| Search changelog | `hx-get="/changelog?q=..."` | `changelog_list.html` |

---

## 6. Theme System

Every colour in the app is a column in the Themes table — no hardcoded colours. A context processor injects the user's resolved theme as CSS custom properties on every page load.

**Fallback chain:** For any NULL column in the selected theme, the Classic (id=0) theme value is used. Templates reference colours via `var(--bg-primary)` etc.

**Guest themes** are stored in the session cookie only. When the session expires, it defaults back to Classic.

---

## 7. Stats Calculation

- **Global averages are viewer-relative.** They are calculated per-request based on the viewing user's `include_featured` and `include_remixes` settings. Two users with different settings see different averages.
- **Scored group threshold** is hardcoded at 80% in `services/stats.py`. An artist counts as a "scored group" for a user if that user has rated 80%+ of the artist's songs.
- **Subunit aggregation:** Subunit songs are included in the parent artist's stats. Soloist songs are not — soloists are standalone.

---

## 8. User Deletion

Multi-step atomic operation in `services/user.py`:

1. Rename the user's personal theme to `deleted_{username}` (other users may have selected it)
2. Delete the User row (cascades to Ratings and UserSettings; SET NULL on Changelog and Themes)
3. Compact `sort_order` — decrement by 1 for all users above the deleted slot, ordered ASC

---

## 9. Deployment (Railway)

- **Procfile:** `web: gunicorn "app:create_app()" --bind 0.0.0.0:$PORT --workers 1`
- **Why 1 worker:** SQLite write-lock contention. Switch to Postgres before increasing workers.
- **Persistent volume** mounted at `/data`. Production DB lives at `/data/arima.db`.
- **First deploy:** Push to GitHub → Railway auto-deploys → `flask seed` in the container. Re-running `flask seed` is idempotent.

---

## 10. Decisions That Can Wait

| Decision | When to Decide |
|---|---|
| Alembic/migrations tooling | If migrations become frequent enough to warrant it |
| Caching layer (Redis, etc.) | If page loads become noticeably slow |
| Rate limiting | If abuse is observed |

---

## 11. Rating Colours & Theme Columns

All rating and heat map colours are theme-driven:

**Rating cell backgrounds:** `rating_5_bg` through `rating_0_bg` (6 columns)
**Rating text:** `rating_text_light` (for dark cells), `rating_text_dark` (for light cells)
**Heat map anchors (average scores):** `heatmap_high`, `heatmap_mid`, `heatmap_low`
**Completion heat map (percentages):** `pct_high`, `pct_mid`, `pct_low`
**Structural:** `album_header_bg`, `row_alternate`, `grid_line`, `key_bg_standard`, `key_bg_stealth`
