# Kpop Rating Database

## Overview

A lightweight web application where a small group of friends can rate music. Originally limited to Kpop but has since expanded. The app is designed for minimal traffic and prioritises simplicity over scalability. Users can submit ratings, browse each other's scores, and see aggregate rankings across the group.

## Backend Architecture Options

### Options Considered

| Framework   | Language | Pros                                                                                                                   | Cons                                                                                           |
|-------------|----------|------------------------------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------|
| **Flask**   | Python   | Micro-framework, minimal boilerplate, Jinja2 templates for server-rendered pages, native SQLite support via SQLAlchemy | Less built-in structure for larger apps                                                        |
| **FastAPI** | Python   | Auto-generated API docs, type validation, async support                                                                | Async/OpenAPI overkill for ~5 users, JSON-only (needs separate frontend)                       |
| **Laravel** | PHP      | Full-featured MVC, Eloquent ORM, Blade templates                                                                       | Heavy for a small app, more Railway config needed, Eloquent prefers MySQL/Postgres over SQLite |

### Decision: Flask + SQLAlchemy + SQLite

Flask is the simplest backend that meets the project's needs. It serves HTML directly via Jinja2 templates (no separate frontend required), connects to SQLite with a one-line config through SQLAlchemy, and deploys to Railway with minimal setup. The micro-framework approach means only pulling in what's needed — no unused machinery. If the project ever outgrows Flask, migrating to FastAPI is straightforward since both are Python.

## Frontend Architecture Options

### Options Considered

| Approach               | How It Works                                                                             | Pros                                                   | Cons                                                                        |
|------------------------|------------------------------------------------------------------------------------------|--------------------------------------------------------|-----------------------------------------------------------------------------|
| **HTMX + Jinja2**      | HTML attributes trigger server requests that swap page fragments inline — no JS to write | Near-zero JS, no build step, perfect Flask integration | Less suited for highly complex client-side state                            |
| **Alpine.js + Jinja2** | Lightweight JS framework for client-side reactivity, sprinkled into templates            | Declarative, small footprint                           | More JS to write than HTMX, some logic duplicated client-side               |
| **React/Vue SPA**      | Separate frontend app consuming a Flask JSON API                                         | Full client-side control                               | Massive overkill — two apps to maintain, build tools, npm, state management |

### Decision: HTMX + Jinja2 + Tailwind CSS

HTMX eliminates full-page reloads without introducing a JavaScript build pipeline. Flask routes return HTML fragments, and HTMX swaps them into the page via simple HTML attributes (e.g., `hx-post="/rate"`, `hx-swap="outerHTML"`). This keeps the entire frontend inside Jinja2 templates — one codebase, no separate frontend app, no bundler. Tailwind CSS handles styling with utility classes, keeping the UI clean without writing custom CSS. No npm or build step required (Tailwind via CDN).

## Hosting Options

### Options Considered

| Platform                      | Cost (USD) | Billing Model                    | Pros                                                                             | Cons                                           |
|-------------------------------|------------|----------------------------------|----------------------------------------------------------------------------------|------------------------------------------------|
| **Railway**                   | $5/mo      | Usage-based (includes $5 credit) | Best DX, git-push deploys, SQLite-friendly via persistent volumes, loved by devs | Usage-based means small overage risk           |
| **Render**                    | $7/mo      | Flat monthly                     | Predictable cost, no surprises, always-on                                        | $2/mo more, slightly less polished DX          |
| **DigitalOcean App Platform** | ~$5/mo     | Flat monthly                     | Trusted brand, predictable                                                       | More complex than needed, less SQLite-friendly |
| **PythonAnywhere**            | $10/mo     | Flat monthly                     | Simple for Flask                                                                 | Price doubled in Jan 2026, dated UI            |
| **Fly.io**                    | ~$3-5/mo   | Usage-based                      | Great SQLite support (LiteFS)                                                    | No free tier, more setup via CLI               |

### Decision: Railway (Hobby Plan — $5 USD/mo)

Railway offers the simplest deploy experience (connect GitHub, push, live) with enough resources for a small friend-group app. The $5/mo subscription includes $5 of usage credit billed by the minute for vCPU, RAM, and storage. With sporadic traffic from ~5-10 users, actual usage should stay within the included credit. Persistent volumes support SQLite as the database — no separate database server needed.

### Domain Setup

The main site (`example.com`) is hosted on GitHub Pages as a static site. The Kpop rating app lives on a subdomain (`kpop.example.com`) pointed at Railway via a CNAME DNS record. This avoids the complexity of path-based routing across different hosts.

## Theme Storage Options

### Options Considered

| Approach              | Pros                                                | Cons                                                                     |
|-----------------------|-----------------------------------------------------|--------------------------------------------------------------------------|
| **Column-per-colour** | Simple queries, explicit schema, easy to understand | Schema migration needed for each new UI colour                           |
| **Key-value table**   | No migrations for new colours, flexible             | Queries are more complex (pivot or multiple lookups), harder to validate |
| **JSON column**       | No migrations, single read per theme, flexible      | No column-level validation, harder to query individual colours           |

### Decision: Column-per-colour (Themes table)

For v1 with ~5 users and a stable UI, schema migrations for new colours are infrequent and trivial. The explicit schema makes queries simple (`SELECT bg_primary FROM themes WHERE id = ?`) and provides column-level type safety. If the UI grows significantly, migrating to a key-value or JSON approach is straightforward.

## Development Environment

### Essentials

- **Python 3.12**
- **pip** (included with Python)
- **Git**
- **VS Code**

### VS Code Extensions

- **Python** (Microsoft) — linting, debugging, IntelliSense
- **Jinja** — template syntax highlighting
- **Tailwind CSS IntelliSense** — utility class autocomplete
- **SQLite Viewer** — browse the database without leaving the editor

## Permissions

| Action                          | Viewer | User          | Editor | Admin |
|---------------------------------|--------|---------------|--------|-------|
| Browse artists, albums, songs   | Yes    | Yes           | Yes    | Yes   |
| View ratings                    | Yes    | Yes           | Yes    | Yes   |
| View stats                      | Yes    | Yes           | Yes    | Yes   |
| Rate songs                      | No     | Yes           | Yes    | Yes   |
| Update own rating               | No     | Yes           | Yes    | Yes   |
| Add artists, albums, songs      | No     | Yes (pending) | Yes    | Yes   |
| Edit artists, albums, songs     | No     | No            | Yes    | Yes   |
| Approve/reject pending changes  | No     | No            | Yes    | Yes   |
| Delete songs/albums/artists     | No     | No            | No     | Yes   |
| Assign user roles               | No     | No            | No     | Yes   |
| Invite users                    | No     | No            | No     | Yes   |

Admin has all permissions. Editor has all permissions that User and Viewer have. User has all permissions that Viewer has.

The **System** role (id=4) is internal only — it is never displayed in the UI, cannot be assigned via the User Management page, and does not appear in the permissions table above. It exists solely to give the System (id=0) and Guest (id=1) accounts a distinct role that is excluded from all user-facing role lists and dropdowns.

## User Stories

### Authentication

- As a visitor, I want to create an account so I can access the app (requires invite from admin).
- As a user, I want to log in and log out so my ratings are tied to my identity.

### Browsing

- As a viewer, I want to browse artists, albums, and songs so I can explore the catalog.
- As a viewer, I want to see the average rating and individual friend ratings on a song so I can compare scores.
- As a viewer, I want to see aggregate ratings rolled up at the album level so I can quickly gauge how an album landed.

### Rating

- As a user, I want to rate a song on a 0-5 scale so I can record my opinion.
- As a user, I want to update my rating on a song so I can change my mind.

### Content Management

- As a user, I want to submit a new album (with its songs and artist) so the group can rate it. Songs must always be submitted as part of an album.
- As an editor, I want to see a queue of user-submitted albums pending approval so I can review them.
- As an editor, I want to approve or reject a pending submission, with the ability to reject individual songs while approving the rest, so only quality entries make it into the catalog.
- As an editor, I want to edit song, album, and artist details so I can fix typos or incorrect info.
- As an admin, I want to add albums via the same submission process, with my submissions auto-approved, so I can manage the catalog quickly.

### User Management

- As an admin, I want to assign roles (Admin, Editor, User, Viewer) to accounts so I can control who can do what.
- As an admin, I want to invite friends to the app so they can create accounts.

## Pages

### Navbar (present on all pages except Login)

- Home
- Artist Stats
- Global Stats
- Artists
- Site Stats [v2 — content TBD]
- Changelog
- Rules
- Views
- Submissions (Editor and Admin only)
- Country dropdown (far right) — "All" (prepended by application code, default, no filter applied) followed by options from the Countries table.
- Genre dropdown (far right) — "All" (prepended by application code, default, no filter applied) followed by options from the Genres table.
- Profile Image (far right)
- Profile (far right)

The Country and Genre dropdowns act as global filters. "All" is the default selection (prepended by application code, not a database row), meaning no filtering is applied. These filters affect the Artists page (see below). The Country filter applies to the list of artists shown in the bottom navbar (filtering by `Artists.country_id`). The Genre filter applies at the album level (filtering by `Album_Genres`).

### Login Page

- On the login page, the user is prompted for username and password. Under the inputs, there are two buttons: "Login as Guest" and "Create Account."
    - **Login as Guest:** Logs into the Guest account (id=1), which has Viewer permissions only.
    - **Create Account:** Replaces the password input with "Email," "Create Password," and "Confirm Password" fields.
        - The email is checked against the Users table. Only pre-invited emails (where the account has not yet been created) are allowed.
            - show error message if the password(hash) column is not null "User Account Already Exists"
            - show error message if the email doenst have an associated user "User Not Invited"
        - **Known issue:** Anyone who knows an invited email address could claim the account before the intended recipient. This is worse than a simple race condition — the malicious claimer permanently locks out the intended user because: (1) the email slot is consumed and cannot be re-invited, (2) the claimer can set any username they want during account creation, and (3) usernames cannot be changed after creation in v1. The legitimate user has no path to create an account for that email. **Recovery flow:** An Admin deletes the fraudulent User row (which cascades to Ratings and User_Settings, sets NULL on submitted content via ON DELETE SET NULL). The Admin then creates a new invite with the same email address — this works because the UNIQUE constraint on email is released when the fraudulent row is deleted. The intended user can then complete account creation normally.  Acceptable tradeoff for v1 given the app's small, trusted user base.
- Upon loading the app (from any URL), the user is redirected to the login page if not logged in.
- Upon successful login, the session is stored in a cookie (30-day expiry).
- Page layout (top to bottom):
    - Moderate gap of empty space
    - Header image
    - A.R.I.M.A. (title)
    - Mission statement
    - Horizontal line
    - Description

### Home Page

- For v1, this page displays only the user-selected home page image, centred horizontally and vertically with a margin on all sides.
- [v2] Allow the user to customise their home page in a special editor (with preview window) on the settings/profile page. Allow CSS and HTML (possibly JS).
    - For example, they may want a large image of their favourite artist and a custom set of stats.

### Artist Stats (was STATS 2.0 in the spreadsheet)
- This page is split into two tables (it is actually one table, but there is a gap between the two main content sections making it appear as two tables).
- Has a shared header with the following columns:
    - The header sits above the top table and is shared between both tables.
    - The header is pinned/frozen so it stays in place when the user scrolls down.
    - | Global Average | Artist | [list of users] | Song Count | [list of users (again)] |

**Top Table**
- Under Artist, there are 4 rows (Overall Average, Total Rated Songs, Rank, Scored Group Count).
    - Scored group count has a tooltip that explains what counts as a "scored group" (for initial release, it is 80% or more rated songs, but will be more complex later). The 80% threshold is intentionally hardcoded in application code — it is not a configurable setting or database value. This is calculated per user — the count of artists where that specific user has rated 80%+ of the artist's songs. **Scored group count is always calculated live against the current song totals.** It is expected to fluctuate: a user's count may increase as they rate more songs, and decrease when new songs are added to an artist (reducing the user's percentage below the threshold). This is intentional — the metric reflects the user's current standing, not a historical snapshot.
    - **Denominator definition ("the artist's songs"):** The song count used as the denominator respects the user's settings: featured songs are included only if `include_featured = true`, remix tracks are included only if `include_remixes = true`. Songs from the artist's subunits are included in the parent's count, but soloist songs are not (soloists have their own row). Unapproved (pending) songs are included in the denominator.
- Under Global Average, there are 4 rows (all averages exclude users with zero rated songs):
    - Overall average % of songs rated
    - Overall average count of rated songs
    - "X"
    - Overall average scored group count
- Under each user's column (first), the stats are shown for the 4 rows:
    - User average % rated
    - User total count of rated songs
    - User rank (by number of rated songs)
    - User scored group count
- Song count shows the total count of songs in the database (centred vertically).

**Bottom Table**
- Each artist shows up as a row.
- Artists with a subunit have a ">" icon indicating that it can be expanded to show subunit(s) as new row(s) beneath it.
    - Soloists don't show up under an artist; they have their own row.
- Global average is the average percentage rated for an artist across all users who have rated at least one of the artist's songs (users with no ratings for the artist are excluded).
    - select * from song inner join artist inner join score where score not null
- Under each user's column (first), the user's percentage of rated songs for the artist is shown.
- Under each user's column (second), the user's count of unrated songs for the artist is shown.
- Song count shows the count of songs that the artist has.
- The artist name is coloured by the artist's gender (colour defined in the theme).

Note: see attached csv for more details

### Global Stats (was STATS in the spreadsheet)
- Has a header with the following columns:
    - | Global Average | Artist | [list of users] | Key |
- Each artist shows up as a row.
- Artists with a subunit have a ">" icon indicating that it can be expanded to show subunit(s) as new row(s) beneath it.
    - Soloists don't show up under an artist; they have their own row.
- Under each user's column, the user's average score for the artist is shown.
- Global average is the average score for an artist across all users who have rated at least one of the artist's songs (users with no ratings for the artist are excluded).
- The header is pinned/frozen so it stays in place when the user scrolls down.
- The artist name is coloured by the artist's gender (colour defined in the theme).

**Header (pinned/frozen):** | Global Average | Artist | [list of users] | Key |

Users are displayed in `sort_order` order.

Each artist is a row. Artists with subunits have a ">" expand icon to reveal subunit rows. Soloists have their own row.

| Column         | Value                                         |
|----------------|-----------------------------------------------|
| Global Average | Average score for the artist across all users who have rated at least one of the artist's songs. Users with no ratings for the artist are excluded from the calculation. |
| Artist         | Artist name, coloured by gender (from theme)  |
| [User]         | User's average score for the artist           |
the user column repeats for all users

Note: see attached csv for more details

### Artists

The Artists page has two parts:

**Bottom Navbar:** A horizontally scrollable list of all artists filtered by the selected Country and Genre. Artist names are coloured by gender (from theme). Selecting an artist loads their discography in the main content area. If all of an artist's albums are filtered out by the selected Genre, that artist is hidden from the navbar.

**Main Content (selected artist's discography):**

| Column          | Description                                                                                                        |
|-----------------|--------------------------------------------------------------------------------------------------------------------|
| Discography     | Albums and their songs. Album names in album colour (from theme). Promoted songs in promoted colour (from theme).  |
| P               | Checkbox per song (checked = promoted by artist/publisher). Tooltip: "Promoted Song"                               |
| [list of users] | User ratings for each song                                                                                         |
| Key             | Legend/key used for rating (repeats)                                                                               |
| Remix           | Toggle to show/hide remix tracks. Shortcut for `include_remixes` — toggling updates the user setting persistently. |

Only albums matching the selected Genre filter are shown (or all albums if "All" is selected). Since albums can have multiple genres, an album appears if **any** of its genres match the selected genre. Only songs belonging to the displayed albums are shown.

If a song features multiple artists, the song (and its album) appears on **each** artist's page.

**Duplicate songs across albums:** A song can appear on multiple albums (e.g., original release and repackage). When this occurs, the song is displayed under each album it belongs to. The song has a single rating per user — editing the rating on one album updates it everywhere. In v1, duplicate songs are shown in full on all albums. [v2] A user setting to hide duplicate songs (showing them only under the earliest album) will be added — see User_Settings `hide_duplicate_songs`.

The last updated date is shown on the page. This is not the date of the last change — it is the date anyone last verified the artist's catalog is complete (no unreleased songs/albums missing).

**Note:** The genre filter applies at the album level. If a Kpop album contains a rock B-side, filtering by "Rock" will not show that album unless it is also tagged as Rock. This is an acceptable tradeoff for simplicity. The Country and Genre filtering involves a multi-table join (Genre → Album_Genres → Album → Album_Song → Song → Artist_Song → Artist); this was considered and is acceptable at the expected scale (~5 users, hundreds of artists).

**Known issue (genre filter and stats):** When a genre filter is active, stats (averages, percentage rated, scored group counts) are computed only from songs on matching albums. This means an artist's displayed average may be based on a small subset of their catalog. This is the expected behaviour — users understand the filter narrows the dataset.

**Global averages are viewer-relative.** Global averages are computed against the viewing user's song set (respecting their `include_featured` and `include_remixes` settings) — they are not precomputed or shared across users. Two users with different settings will see different Global Average values for the same artist.

**Unapproved items:** Unapproved (pending) artists, albums, and songs are always visible on all pages (Artists, Stats, etc.). An item is pending if its `submission_id` references a Submission with `status = 'pending'`. Pending items are visually distinguished from approved items (e.g., different background colour, opacity, or a "pending" badge — styled via the theme). Users can rate pending songs. Pending items include a link to the Submissions page so editors/admins can quickly navigate to approve or edit them. This ensures content is immediately useful upon submission, even before approval.

### Rules

- User-authored content managed by Editors and Admins.
- Visible to all roles (Users need to see rules before making submissions).
- Covers rules for submissions, formatting, what should/shouldn't be added, etc.
- Displays the rules content as rendered text.
- Editors and Admins see an "Edit" button. Clicking it replaces the rendered text with an editable text field and the "Edit" button changes to a "Save" button. Clicking "Save" persists the content and switches back to rendered view.
- Content is stored in the Rules table (see Database Tables).

### Changelog

| Column        | Description                                                                                                                                                                          |
|---------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Date          | When the change was made                                                                                                                                                             |
| User          | Who submitted the change                                                                                                                                                             |
| Approved By   | The approving Editor/Admin's name. For auto-approved changes (Editor/Admin submissions), shows "(auto)". For pending changes, shows "(pending)" with a link to the Submissions page. |
| Description   | What changed (e.g., "Added album 'Biggest Fan' for Irene", "Removed song 'MOVEURBODY' from HYO album 'Banger'")                                                                      |
| Justification | Required for removals (e.g., "duplicate album"). Optional otherwise.                                                                                                                 |

Logged changes: album add/removal, song add/removal, artist add/removal, song rejection from a submission.

- Search field at the top to filter by album/artist.
- Changelog entries are **never deleted**. When a submission is rejected or items are deleted, the corresponding changelog entries survive with their foreign keys set to NULL (via ON DELETE SET NULL). The description field retains the human-readable record of what happened.
- [Open question] Should changelog entries be auto-generated? Want to group changes into logical groupings to simplify somehow as well.

### Add Artist Page
- Looks similar to a standard srtist page but starts empty and the user imputs albums and songs

### Submissions

- Only visible to Editor and Admin.
- Shows pending submissions as a list with a search field at the top.
- Each submission is expandable to show all items it contains (artist, albums, songs).
- Editors/Admins can edit a submission before approving (e.g., fixing formatting).

**Line-by-line rejection:** Editors can reject individual songs within a submission. The UI presents each song with a checkbox or reject button. This allows the editor to cherry-pick which items survive approval.

**Approval flow:**
1. Editor reviews the submission and optionally marks individual songs for rejection.
2. Editor clicks "Approve."
3. A confirmation modal displays:
    - Items that will be approved (album, remaining songs, artist if new).
    - Items that will be rejected and deleted (marked songs and their ratings).
4. On confirm:
    - Approved items: The album, non-rejected songs, and the artist (if newly created) remain linked to the Submission. Their approval status is derived from the Submission's `status`.
    - Rejected songs: The song and its ratings are deleted. A changelog entry is created for each rejected song (e.g., "Song 'X' rejected from submission #Y").
    - The Submission record: `status = 'approved'`, `approved_by_id` and `approved_at` are set.

**Full rejection flow:**
1. Editor clicks "Reject" on the entire submission.
2. Editor must provide a `rejected_reason`.
3. A confirmation modal displays every row that will be deleted (artist, albums, songs, ratings) with Confirm and Cancel buttons.
4. On confirm:
    - All items created by the submission are deleted (artist, albums, songs, ratings).
    - Changelog entries referencing deleted items survive (foreign keys become NULL via ON DELETE SET NULL). A new changelog entry is created: "Submission #Y rejected: [reason]".
    - The Submission record: `status = 'rejected'`, `rejected_by_id`, `rejected_at`, and `rejected_reason` are set. The Submission row itself is never deleted — it serves as the permanent audit record.
- [v2] Before deletion, also send an email to affected users listing the deleted artist/album/song and their lost ratings in a summary table. Not implemented in v1.

**Auto-approval:** Editor and Admin submissions are auto-approved (`status = 'approved'`, `approved_by_id` set to the System user id=0). Approval status is derived from the Submission — no separate flag on entities.

### Views

- list of different views to select from
- An admin/editor/debug page showing orphaned data: songs not linked to any album (via Album_Song), and any other data integrity issues. Only visible to Editor and Admin — other roles are redirected.
- Accessible from the navbar (Editor and Admin only).

### Themes

- Lists all themes with a preview of all colours: Classic, Dark, and each user's personal theme.
- Classic (light) and Dark Mode themes are Admin-editable only.
- Users can edit their own personal theme.

### User Management Page

- Admin only — other users are redirected to the home page (or login page if not logged in).
- Shows a list of all users ordered by join date.
- Columns: | Username | Role | Email | Join Date | Last Seen | Profile Image |
- Role column has a dropdown for changing roles. The dropdown only shows assignable roles (Admin, Editor, User, Viewer). The System role (id=4) is never shown.
- **Protected accounts:** The System (id=0) and Guest (id=1) accounts cannot be deleted or have their roles changed. Application code on the User Management page doesnt show these accounts.
- "+" icon at the bottom to invite a new user: input fields for username and email, a role dropdown, and an "Invite" button that sends an invitation email.

### Profile

- User settings and profile page.
- Change profile picture.
- Select theme.
- Toggle `include_featured` — whether featured songs are included in stats and displayed on Artists pages.
- Toggle `include_remixes` — whether remix tracks are included in stats and displayed on Artists pages. (Also controllable via the remix toggle on the Artists page.)
- [v2] Select which users are shown (for the current user) on Artists and Stats pages.
- [v2] Reorder users (for the current user) on Artists and Stats pages.

## Database Tables

### General Conventions

- **AUTOINCREMENT:** Tables with `INTEGER PRIMARY KEY AUTOINCREMENT` are noted below. SQLite's AUTOINCREMENT guarantees IDs are never reused, even after deletion. Lookup tables with manually assigned IDs do not use AUTOINCREMENT. **Seeding:** All default/reserved rows (e.g., Users id 0-2, Submissions id 0) are inserted via seed script after table creation. The seed script must update `sqlite_sequence` to the highest seeded ID so that subsequent AUTOINCREMENT inserts start above the reserved range.
- **NOT NULL:** All columns are NOT NULL unless explicitly marked as "Nullable."
- **DEFAULT:** Columns with a default value are noted. Columns without a default must be explicitly set on insert.
- **ON DELETE behaviour:** Foreign keys use different ON DELETE strategies depending on the relationship:
    - `ON DELETE CASCADE`: Used where child rows have no meaning without the parent (e.g., Ratings → Users, Ratings → Songs, User_Settings → Users, Album_Song → Albums/Songs, Artist_Song → Artists/Songs, Album_Genres → Albums/Genres).
    - `ON DELETE SET NULL`: Used where the row should survive the deletion of the referenced entity (e.g., `submitted_by_id` on Artists/Albums/Songs/Submissions, `user_id` and `approved_by_id` on Changelog, `user_id` on Themes). These columns must be nullable.
    - `ON DELETE RESTRICT`: Used where deletion of the parent should be blocked if children still reference it (e.g., `submission_id` on Artists/Albums/Songs — Submissions are audit records and must not be deleted while referenced).
    - Each foreign key's ON DELETE behaviour is documented in the table where it is defined. If not explicitly stated, assume `ON DELETE CASCADE`.
- **User list filtering:** System (id=0) and Guest (id=1) accounts are excluded from all user lists in the app (Stats, Artists, User Management). To determine exclusion, check `email IS NULL`.
- **Deletion confirmation:** All delete and rejection actions display a modal listing every row that will be affected (cascaded deletes, lost ratings, etc.) with Confirm and Cancel buttons. The deletion only proceeds on Confirm.

### Reserved User IDs

IDs 0-2 are reserved for system and special accounts. Real user IDs start at 3 (AUTOINCREMENT).

| ID | Username      | Purpose                                                        |
|----|---------------|----------------------------------------------------------------|
| 0  | (auto)        | System user. Used as `approved_by_id` for auto-approved items. |
| 1  | Guest         | Shared guest account with Viewer permissions.                  |
| 2  | Stealth       | Default admin account.                                         |

### Users

| Column          | Type    | Notes                                                                                                                                    |
|-----------------|---------|------------------------------------------------------------------------------------------------------------------------------------------|
| id              | INTEGER | Primary key. AUTOINCREMENT. IDs 0-2 are manually inserted; sequence starts at 3.                                                         |
| username        | TEXT    | NOT NULL. Unique. Set by Admin at invite; editable by user on account creation only. Cannot be changed after account creation in v1.     |
| email           | TEXT    | Nullable. Unique. NULL for system/special accounts (ids 0-1). Used to determine user list exclusion (`email IS NULL` = excluded).        |
| password        | TEXT    | Nullable. Bcrypt hash (see Authentication section). NULL for system accounts and invited-but-uncreated accounts.                         |
| role_id         | INTEGER | NOT NULL. Foreign key to Roles.                                                                                                          |
| created_at      | TEXT    | NOT NULL. Auto-set on row creation.                                                                                                      |
| last_seen       | TEXT    | Nullable. Updated on login or edit. NULL until first login. Not updated for "System" users.                                              |
| sort_order      | INTEGER | Nullable. Unique. Controls display order of users on Stats and Artists pages. NULL = excluded from user lists (system/special accounts). |
| profile_image   | TEXT    | Nullable.                                                                                                                                |
| home_page_image | TEXT    | Nullable.                                                                                                                                |

Note: For `sort_order`, new users are assigned the next highest value (appended to the end of the list).

Foreign keys: `role_id` → Roles(`id`).

**User deletion behaviour:** When a user is deleted, only the following are removed:
- The User row itself.
- The user's Ratings (via ON DELETE CASCADE on `Ratings.user_id`).
- The user's User_Settings row (via ON DELETE CASCADE on `User_Settings.user_id`).

Everything else the user created (Artists, Albums, Songs, Submissions, Changelog entries) **survives deletion**. The `submitted_by_id` columns on those tables are set to NULL (via ON DELETE SET NULL), preserving the content while removing the link to the deleted user. The user's personal Theme row also survives — see Themes table for details.

Default data:

| id | username      | email      | password   | role_id | sort_order |
|----|---------------|------------|------------|---------|------------|
| 0  | (auto)        | NULL       | NULL       | 4       | NULL       |
| 1  | Guest         | NULL       | NULL       | 3       | NULL       |
| 2  | Stealth       | [Redacted] | [Redacted] | 0       | 1          |

### User_Settings

User preferences are stored in a separate table. Each user has at most one row. System (id=0) and Guest (id=1) do **not** have a User_Settings row — their preferences are stored in the session cookie only (ephemeral, per-browser, lost on session expiry). When no User_Settings row exists for a user, application code falls back to cookie-stored values or defaults (country=NULL/All, genre=NULL/All, theme=Classic, include_featured=false, include_remixes=false, hide_duplicate_songs=false).

| Column               | Type    | Notes                                                                                                                                                                                            |
|----------------------|---------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| user_id              | INTEGER | Primary key. Foreign key to Users. ON DELETE CASCADE.                                                                                                                                            |
| country              | INTEGER | Nullable. DEFAULT NULL. Foreign key to Countries. User's country filter. NULL = "All" (no filter applied).                                                                                       |
| genre                | INTEGER | Nullable. DEFAULT NULL. Foreign key to Genres. User's genre filter. NULL = "All" (no filter applied).                                                                                            |
| include_featured     | BOOLEAN | NOT NULL. DEFAULT false. Whether featured songs count in user's stats and scored group denominator.                                                                                              |
| include_remixes      | BOOLEAN | NOT NULL. DEFAULT false. Whether remix tracks count in user's stats and scored group denominator. Also controls visibility of remix tracks on the Artists page (equivalent to the remix toggle). |
| theme                | INTEGER | NOT NULL. DEFAULT 0. Foreign key to Themes. Defaults to Classic (id=0).                                                                                                                          |
| hide_duplicate_songs | BOOLEAN | NOT NULL. DEFAULT false. [v2] When true, songs appearing on multiple albums are shown only under the earliest album. Not implemented in v1 — column exists for forward compatibility.            |

Foreign keys: `user_id` → Users(`id`) ON DELETE CASCADE, `country` → Countries(`id`), `genre` → Genres(`id`), `theme` → Themes(`id`).

A User_Settings row is created when a user completes account creation (not at invite time). On user deletion, the row is automatically removed via ON DELETE CASCADE.

### Roles

| Column | Type    | Notes                        |
|--------|---------|------------------------------|
| id     | INTEGER | Primary key.                 |
| role   | TEXT    | NOT NULL. Unique. Role name. |

Default data:

| id | role   |
|----|--------|
| 0  | Admin  |
| 1  | Editor |
| 2  | User   |
| 3  | Viewer |
| 4  | System |

The **System** role (id=4) is an internal role that is never displayed in the UI. It cannot be assigned via the User Management page and does not appear in any role dropdown. It exists solely to distinguish System (id=0) and Guest (id=1) accounts from real users. Application code must filter it out of all user-facing role lists. The role dropdown on the User Management page only shows ids 0-3.

### Themes

Every colour used in the app is a column in this table. No hardcoded colours — all colours are theme-driven. See [Theme Storage Options](#theme-storage-options) for alternatives considered.

| Column           | Type    | Notes                                                                                                                                         |
|------------------|---------|-----------------------------------------------------------------------------------------------------------------------------------------------|
| id               | INTEGER | Primary key. AUTOINCREMENT.                                                                                                                   |
| name             | TEXT    | Nullable. Display name for the theme. NULL for user-created themes (UI derives the name from the owning user's username + "'s Theme").        |
| user_id          | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. The user who owns this theme. NULL for system themes (Classic, Dark) and orphaned themes. |
| bg_primary       | TEXT    | Nullable. Primary background colour.                                                                                                          |
| bg_secondary     | TEXT    | Nullable. Secondary background colour.                                                                                                        |
| text_primary     | TEXT    | Nullable. Primary text colour.                                                                                                                |
| text_secondary   | TEXT    | Nullable. Secondary text colour.                                                                                                              |
| navbar_bg        | TEXT    | Nullable. Navbar background colour.                                                                                                           |
| navbar_text      | TEXT    | Nullable. Navbar text colour.                                                                                                                 |
| header_row       | TEXT    | Nullable. Header row background colour.                                                                                                       |
| promoted_song    | TEXT    | Nullable. Promoted song highlight colour.                                                                                                     |
| gender_female    | TEXT    | Nullable. Female artist name colour.                                                                                                          |
| gender_male      | TEXT    | Nullable. Male artist name colour.                                                                                                            |
| gender_mixed     | TEXT    | Nullable. Mixed group artist name colour.                                                                                                     |
| album_name       | TEXT    | Nullable. Album name colour (used on Artists page).                                                                                           |
| pending_item     | TEXT    | Nullable. Background/highlight colour for pending (unapproved) items.                                                                         |
| link             | TEXT    | Nullable. Link colour.                                                                                                                        |
| button_primary   | TEXT    | Nullable. Primary button colour.                                                                                                              |
| button_secondary | TEXT    | Nullable. Secondary button colour.                                                                                                            |
| border           | TEXT    | Nullable. Border colour.                                                                                                                      |
| ...              | TEXT    | Nullable. (additional as needed)                                                                                                              |

All colour columns are nullable. If a column is NULL for the selected theme, the Classic (id=0) theme colour is used as fallback (in application code, not in the DB). **Known risk:** If Classic's row is corrupted (NULL values), the fallback chain breaks. This risk is accepted — Classic and Dark rows are admin-managed and validated manually. **Recommendation:** The seed script should assert that Classic (id=0) and Dark (id=1) have all colour columns populated. Application code should log a warning on startup if any Classic colour column is NULL.

Foreign keys: `user_id` → Users(`id`) ON DELETE SET NULL.

- Classic (light mode) is id=0 (`name = 'Classic'`, `user_id = NULL`). Dark Mode is id=1 (`name = 'Dark'`, `user_id = NULL`). These two rows must have all colour columns populated (no NULLs). Each is a standalone theme — there is no automatic light/dark toggle. Users explicitly select one theme.
- Each user gets their own theme row on account creation (defaults to all NULLs, which renders identically to Classic via fallback). The `user_id` column links the theme to the owning user.
- The theme selector on the Profile page lists: Classic, Dark, the current user's personal theme, and every other user's personal theme. All are selectable.
- When new UI elements need a colour, a new column is added.

**User deletion and themes:** When a user is deleted, their personal theme row survives (other users may have selected it). Before deleting the user, application code sets the theme's `name` to `"deleted_" + username` (e.g., `"deleted_Stealth"`). After deletion, `user_id` becomes NULL via ON DELETE SET NULL. The theme remains selectable by other users under its new name.

### Countries

| Column  | Type    | Notes                           |
|---------|---------|---------------------------------|
| id      | INTEGER | Primary key.                    |
| country | TEXT    | NOT NULL. Unique. Country name. |

Default data:

| id | country  |
|----|----------|
| 0  | Korean   |
| 1  | Japanese |
| 2  | Canadian |
| 3  | American |
| 4  | Latin    |

"All" is not stored in the database. It is prepended to the Country dropdown in the UI by application code and represents "no filter applied" (i.e., show all countries).

**Known issue (intentional):** "Country" refers to the artist's country of origin (`Artists.country_id`), not the language or market of individual songs/albums. A Korean artist releasing a Japanese-language album will still appear under "Korean." This is intentional and understood by the user base.

### Genres

| Column | Type    | Notes                         |
|--------|---------|-------------------------------|
| id     | INTEGER | Primary key.                  |
| genre  | TEXT    | NOT NULL. Unique. Genre name. |

Default data:

| id | genre |
|----|-------|
| 0  | Kpop  |
| 1  | Jpop  |
| 2  | Pop   |
| 3  | Rock  |
| 4  | Metal |

"All" is not stored in the database. It is prepended to the Genre dropdown in the UI by application code and represents "no filter applied" (i.e., show all genres).

### Submissions

A Submission is the grouping entity that ties together all items created in a single user action (e.g., submitting an album with its songs and optionally a new artist). Every Artist, Album, and Song created through the submission flow references the Submission via `submission_id`.

| Column          | Type    | Notes                                                                                                                                 |
|-----------------|---------|---------------------------------------------------------------------------------------------------------------------------------------|
| id              | INTEGER | Primary key. AUTOINCREMENT.                                                                                                           |
| submitted_by_id | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. Who created the submission.                                                       |
| submitted_at    | TEXT    | NOT NULL. When the submission was created.                                                                                            |
| status          | TEXT    | NOT NULL. DEFAULT 'pending'. One of: 'pending', 'approved', 'rejected'.                                                               |
| approved_by_id  | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. Set when status = 'approved'. Set to System (id=0) for auto-approved submissions. |
| approved_at     | TEXT    | Nullable. When the submission was approved.                                                                                           |
| rejected_by_id  | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. Set when status = 'rejected'.                                                     |
| rejected_at     | TEXT    | Nullable. When the submission was rejected.                                                                                           |
| rejected_reason | TEXT    | Nullable. Required when status = 'rejected'. Human-readable reason for rejection.                                                     |

Foreign keys: `submitted_by_id` → Users(`id`) ON DELETE SET NULL, `approved_by_id` → Users(`id`) ON DELETE SET NULL, `rejected_by_id` → Users(`id`) ON DELETE SET NULL.

The Submission row is **never deleted**. Even after rejection (and the subsequent deletion of its child items), the Submission row persists as a permanent audit record showing who submitted what, when, who reviewed it, and why it was rejected. Foreign keys referencing Submissions (`submission_id` on Artists, Albums, Songs) use `ON DELETE RESTRICT` — attempting to delete a Submission will fail if any child entities still reference it, preventing accidental orphaning or silent approval changes.

**Seed Submission (id=0):** A reserved Submission row (id=0, `status = 'approved'`, `submitted_by_id = 0`, `approved_by_id = 0`) is inserted by the seed script. All legacy and seed data references this Submission via `submission_id = 0`. This eliminates the need to treat NULL as "implicitly approved" — every entity has an explicit Submission, and approval is always derived from the Submission's `status`.

### Artists

| Column          | Type    | Notes                                                                                                                                                          |
|-----------------|---------|----------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id              | INTEGER | Primary key. AUTOINCREMENT.                                                                                                                                    |
| name            | TEXT    | NOT NULL. Duplicates allowed (different artists can share a name).                                                                                             |
| gender_id       | INTEGER | NOT NULL. Foreign key to Group_Gender.                                                                                                                         |
| country_id      | INTEGER | NOT NULL. Foreign key to Countries.                                                                                                                            |
| submitted_by_id | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. Who originally submitted the entity.                                                                       |
| submission_id   | INTEGER | NOT NULL. Foreign key to Submissions. ON DELETE RESTRICT. The submission this artist was created as part of. Legacy/seed data uses the seed Submission (id=0). |
| last_updated    | TEXT    | Nullable. Date the artist's catalog was last verified complete.                                                                                                |
| is_disbanded    | BOOLEAN | NOT NULL. DEFAULT false.                                                                                                                                       |

Foreign keys: `gender_id` → Group_Gender(`id`), `country_id` → Countries(`id`), `submitted_by_id` → Users(`id`) ON DELETE SET NULL, `submission_id` → Submissions(`id`) ON DELETE RESTRICT.

`submitted_by_id` records who originally submitted the entity. It is nullable and uses ON DELETE SET NULL so that submitted content survives user deletion. Duplicate artist submissions (same real-world artist) create separate rows with different IDs — deduplication is handled manually via approval/rejection, not enforced at the database level. **[v2] A merge operation is needed to combine duplicate artist entries that slip through approval (consolidating songs, ratings, and relationships under a single artist row).**

### Songs

| Column          | Type    | Notes                                                                                                                                                        |
|-----------------|---------|--------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id              | INTEGER | Primary key. AUTOINCREMENT.                                                                                                                                  |
| name            | TEXT    | NOT NULL. Song name.                                                                                                                                         |
| submitted_by_id | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL.                                                                                                          |
| submission_id   | INTEGER | NOT NULL. Foreign key to Submissions. ON DELETE RESTRICT. The submission this song was created as part of. Legacy/seed data uses the seed Submission (id=0). |
| is_promoted     | BOOLEAN | NOT NULL. DEFAULT false.                                                                                                                                     |
| is_remix        | BOOLEAN | NOT NULL. DEFAULT false.                                                                                                                                     |

Foreign keys: `submitted_by_id` → Users(`id`) ON DELETE SET NULL, `submission_id` → Submissions(`id`) ON DELETE RESTRICT.

Songs are always created as part of an album submission. The relationship between songs and artists is managed through the Artist_Song pivot table. The relationship between songs and albums is managed through the Album_Song pivot table.

**Orphan prevention:** Songs must always be created within a transaction that also creates the corresponding Album_Song row. There is no application flow that creates a standalone song. A song cannot exist without at least one album association — if the last Album_Song link would be removed, the operation must be blocked or the song must be deleted. The Views page provides visibility into any orphaned songs (songs with no Album_Song entry) for admin monitoring.

### Albums

| Column          | Type    | Notes                                                                                                                                                         |
|-----------------|---------|---------------------------------------------------------------------------------------------------------------------------------------------------------------|
| id              | INTEGER | Primary key. AUTOINCREMENT.                                                                                                                                   |
| name            | TEXT    | NOT NULL. Album name.                                                                                                                                         |
| release_date    | TEXT    | NOT NULL. Release date.                                                                                                                                       |
| album_type_id   | INTEGER | NOT NULL. Foreign key to Album_Types.                                                                                                                         |
| submitted_by_id | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL.                                                                                                           |
| submission_id   | INTEGER | NOT NULL. Foreign key to Submissions. ON DELETE RESTRICT. The submission this album was created as part of. Legacy/seed data uses the seed Submission (id=0). |

Foreign keys: `album_type_id` → Album_Types(`id`), `submitted_by_id` → Users(`id`) ON DELETE SET NULL, `submission_id` → Submissions(`id`) ON DELETE RESTRICT.

Albums are not directly linked to an artist. On the Artists page, songs are grouped by album via the Album_Song pivot. An album is an organisational container for songs — if two artists share a song, that song's album appears on both artists' pages.

### Ratings

| Column  | Type    | Notes                                                                          |
|---------|---------|--------------------------------------------------------------------------------|
| song_id | INTEGER | NOT NULL. Foreign key to Songs. Part of composite primary key.                 |
| user_id | INTEGER | NOT NULL. Foreign key to Users. Part of composite primary key.                 |
| rating  | INTEGER | NOT NULL. CHECK (rating >= 0 AND rating <= 5). 0 = lowest. No row = unrated.   |
| note    | TEXT    | Nullable. Short comment visible to all users (shown on hover on Artists page). |

Primary key: (`song_id`, `user_id`).

Foreign keys: `song_id` → Songs(`id`) ON DELETE CASCADE, `user_id` → Users(`id`) ON DELETE CASCADE.

Both foreign keys use ON DELETE CASCADE: deleting a song removes all its ratings, and deleting a user removes all their ratings. This is intentional — ratings have no meaning without both the song and the user.

### Album_Types

| Column      | Type    | Notes                              |
|-------------|---------|------------------------------------|
| id          | INTEGER | Primary key.                       |
| type        | TEXT    | NOT NULL. Unique. Album type name. |
| description | TEXT    | Nullable. Description of the type. |

Default data:

| id | type   | description                                                          |
|----|--------|----------------------------------------------------------------------|
| 0  | Album  | A normal album, typically longer than 30 minutes (~8+ songs)         |
| 1  | EP     | A short album, typically under 30 minutes (~3-7 songs)               |
| 2  | Single | A single song released alone (sometimes with 1-2 accompanying songs) |

### Artist_Relationships

| Column       | Type    | Notes                                |
|--------------|---------|--------------------------------------|
| id           | INTEGER | Primary key.                         |
| relationship | TEXT    | NOT NULL. Unique. Relationship type. |

Default data:

| id | relationship |
|----|--------------|
| 0  | Subunit      |
| 1  | Soloist      |

### Group_Gender

| Column | Type    | Notes                          |
|--------|---------|--------------------------------|
| id     | INTEGER | Primary key.                   |
| gender | TEXT    | NOT NULL. Unique. Gender name. |

Default data:

| id | gender |
|----|--------|
| 0  | Female |
| 1  | Male   |
| 2  | Mixed  |

### Changelog

| Column         | Type    | Notes                                                                                                                                 |
|----------------|---------|---------------------------------------------------------------------------------------------------------------------------------------|
| id             | INTEGER | Primary key. AUTOINCREMENT.                                                                                                           |
| date           | TEXT    | NOT NULL. When the change was made.                                                                                                   |
| user_id        | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. Who made the change. NULL if the user has been deleted.                           |
| approved_by_id | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. Set to 0 (System user) for auto-approved changes. NULL while pending.             |
| submission_id  | INTEGER | Nullable. Foreign key to Submissions. ON DELETE SET NULL. The submission this change was part of, if any.                             |
| artist_id      | INTEGER | Nullable. Foreign key to Artists. ON DELETE SET NULL. The artist this change relates to, if any. NULL if the artist has been deleted. |
| album_id       | INTEGER | Nullable. Foreign key to Albums. ON DELETE SET NULL. The album this change relates to, if any. NULL if the album has been deleted.    |
| song_id        | INTEGER | Nullable. Foreign key to Songs. ON DELETE SET NULL. The song this change relates to, if any. NULL if the song has been deleted.       |
| description    | TEXT    | NOT NULL. Human-readable description of the change.                                                                                   |
| justification  | TEXT    | Nullable. Required for removals.                                                                                                      |

Foreign keys: `user_id` → Users(`id`) ON DELETE SET NULL, `approved_by_id` → Users(`id`) ON DELETE SET NULL, `submission_id` → Submissions(`id`) ON DELETE SET NULL, `artist_id` → Artists(`id`) ON DELETE SET NULL, `album_id` → Albums(`id`) ON DELETE SET NULL, `song_id` → Songs(`id`) ON DELETE SET NULL.

**Changelog entries are never deleted.** When referenced items are deleted (via rejection or any other means), the nullable foreign keys become NULL via ON DELETE SET NULL, but the row and its `description` field survive as a permanent audit record. A changelog entry may reference one or more of artist/album/song depending on the scope of the change (e.g., adding an album sets `album_id`; adding a song sets both `album_id` and `song_id`).

### Rules

| Column         | Type    | Notes                                                                                           |
|----------------|---------|-------------------------------------------------------------------------------------------------|
| id             | INTEGER | Primary key. Single row (id=1).                                                                 |
| content        | TEXT    | NOT NULL. The rules content displayed on the Rules page.                                        |
| last_edited_by | INTEGER | Nullable. Foreign key to Users. ON DELETE SET NULL. The Editor/Admin who last edited the rules. |
| last_edited_at | TEXT    | Nullable. When the rules were last edited. NULL until first edit.                               |

Foreign keys: `last_edited_by` → Users(`id`) ON DELETE SET NULL.

This table holds a single row containing the rules content. The seed script inserts the initial row (id=1) with empty or placeholder content. Application code reads and updates this single row — no additional rows are created.

## Pivot Tables and Indexes

### Artist_Artist

| Column       | Type    | Notes                                                     |
|--------------|---------|-----------------------------------------------------------|
| artist_1     | INTEGER | NOT NULL. Foreign key to Artists. The parent/main artist. |
| artist_2     | INTEGER | NOT NULL. Foreign key to Artists. The subunit or soloist. |
| relationship | INTEGER | NOT NULL. Foreign key to Artist_Relationships.            |

Primary key: (`artist_1`, `artist_2`). An artist can only have one relationship type with another artist.

Foreign keys: `artist_1` → Artists(`id`) ON DELETE CASCADE, `artist_2` → Artists(`id`) ON DELETE CASCADE, `relationship` → Artist_Relationships(`id`).

**Parent deletion behaviour:** When a parent artist (`artist_1`) is deleted, the Artist_Artist row is CASCADE-deleted, but the child artist (`artist_2`) survives as a standalone artist. The child is not automatically deleted — if the subunit should also be removed, it must be deleted separately by an admin. This is intentional: subunits may have their own songs, ratings, and history worth preserving independently.

### Artist_Song

| Column         | Type    | Notes                                                  |
|----------------|---------|--------------------------------------------------------|
| artist_id      | INTEGER | NOT NULL. Foreign key to Artists.                      |
| song_id        | INTEGER | NOT NULL. Foreign key to Songs.                        |
| artist_is_main | BOOLEAN | NOT NULL. true = main artist, false = featured artist. |

Primary key: (`artist_id`, `song_id`).

Foreign keys: `artist_id` → Artists(`id`) ON DELETE CASCADE, `song_id` → Songs(`id`) ON DELETE CASCADE.

### Album_Song

| Column       | Type    | Notes                                                                |
|--------------|---------|----------------------------------------------------------------------|
| album_id     | INTEGER | NOT NULL. Foreign key to Albums.                                     |
| song_id      | INTEGER | NOT NULL. Foreign key to Songs.                                      |
| track_number | INTEGER | NOT NULL. UNIQUE(`album_id`, `track_number`). Position on the album. |

Primary key: (`album_id`, `song_id`).

A song can appear on multiple albums (e.g., original release and repackage).

Foreign keys: `album_id` → Albums(`id`) ON DELETE CASCADE, `song_id` → Songs(`id`) ON DELETE CASCADE.

### Album_Genres

| Column   | Type    | Notes                            |
|----------|---------|----------------------------------|
| album_id | INTEGER | NOT NULL. Foreign key to Albums. |
| genre_id | INTEGER | NOT NULL. Foreign key to Genres. |

Primary key: (`album_id`, `genre_id`).

Foreign keys: `album_id` → Albums(`id`) ON DELETE CASCADE, `genre_id` → Genres(`id`) ON DELETE CASCADE.

**Known limitation:** Genre is assigned at the album level, not per song. If a Kpop album contains a rock B-side, it is still tagged as Kpop only (unless explicitly multi-tagged). Acceptable tradeoff for simplicity.

### Indexes

Composite primary keys and UNIQUE constraints create implicit indexes. The following additional indexes are needed for common query paths:

- `artist_song(song_id)` — reverse lookup: which artists perform a song.
- `album_song(song_id)` — orphan detection (Views page) and reverse lookup: which albums contain a song.
- `album_genres(genre_id)` — genre filter queries.
- `artists(country_id)` — Artists bottom navbar filter by country.
- `artists(submission_id)` — lookup all artists in a submission.
- `albums(submission_id)` — lookup all albums in a submission.
- `songs(submission_id)` — lookup all songs in a submission.
- `changelog(artist_id)` — lookup history for an artist.
- `changelog(album_id)` — lookup history for an album.
- `changelog(song_id)` — lookup history for a song.
- `changelog(submission_id)` — lookup all changelog entries for a submission.

## Authentication

### Approach

- **Flask-Login** handles session management, login/logout, and route protection.
- Passwords are hashed using **bcrypt** (via Flask-Bcrypt). Bcrypt generates a unique random salt per hash internally.
- A server-side **pepper** (a secret string stored in an environment variable, not in code or database) is prepended to the password before hashing. This adds a layer of protection: even if the database is compromised, hashes cannot be cracked without the pepper.
- Plaintext passwords are never stored.
- Sessions are stored in a **signed cookie** (Flask's `SECRET_KEY` prevents tampering). Cookie expiry is 30 days.
- All routes redirect to the login page if the user is not authenticated.
- Usernames cannot be changed after account creation in v1.

### Login Flow

1. User enters username and password.
2. Server looks up user by username, prepends the pepper to the entered password, and verifies against the stored bcrypt hash.
3. On success, Flask-Login creates a session cookie. The user is redirected to the home page.
4. On failure, an error message is shown. No indication of whether the username or password was wrong (prevents enumeration).

### Guest Access

- "Login as Guest" button logs into the shared Guest account (id=1) with Viewer permissions. This allows users to quickly check stats and ratings without needing to log in with credentials.
- The Guest account cannot be deleted or have its role changed.
- The Guest user has no User_Settings row. All Guest preferences (country filter, genre filter) are stored in the session cookie only (ephemeral, per-browser, lost on session expiry). Application code never writes to the database for Guest preferences.
- **Note:** The Guest account has `password = NULL`, which is structurally identical to an invited-but-uncreated account. However, Guest is reliably distinguished by `email IS NULL` — invited accounts always have an email. Application code that checks for uncreated accounts must use `password IS NULL AND email IS NOT NULL` (not `password IS NULL` alone).

### Account Creation

- Only available via Admin invite. The Admin enters a username and email on the User Management page, which sends an invite email.
- On the login page, "Create Account" prompts for email, username, password, and confirm password.
- When the user enters their email, it is checked against the Users table. If a matching invited row is found (`password IS NULL AND email IS NOT NULL`), the username field is pre-populated with the Admin-assigned username (as a suggestion — the user may edit it). The form's submit button is disabled until the user has interacted with the username field (either confirming or editing the suggestion). This ensures the user consciously acknowledges their username choice.
- The username is checked for uniqueness on submission. On success, the Users row is updated with the new username (if changed), password hash, and account creation timestamp.
- On successful account creation, a User_Settings row is created for the user with default values, and a personal Theme row is created (all colour columns NULL, rendering identically to Classic via fallback).
- **Known issue:** Anyone who knows an invited email address could claim the account before the intended recipient. This is worse than a simple race condition — the malicious claimer permanently locks out the intended user because: (1) the email slot is consumed and cannot be re-invited, (2) the claimer can set any username they want during account creation, and (3) usernames cannot be changed after creation in v1. The legitimate user has no path to create an account for that email. **Recovery flow:** An Admin deletes the fraudulent User row (which cascades to Ratings and User_Settings, sets NULL on submitted content via ON DELETE SET NULL). The Admin then creates a new invite with the same email address — this works because the UNIQUE constraint on email is released when the fraudulent row is deleted. The intended user can then complete account creation normally. Acceptable tradeoff for v1 given the app's small, trusted user base.

### Route Protection

- Each route checks the user's role before rendering. Unauthorised access redirects to the home page.
- Admin-only pages (User Management, Theme editing) return a redirect, not a 403, to avoid leaking page existence.

## Backend Implementation Notes

- Song creation is always performed within a database transaction that also creates the Album_Song entry, ensuring no orphaned songs.
- The Views page queries for songs with no Album_Song entry to surface any data integrity issues.
- **Submissions:** Every user-submitted album (with its songs and optionally a new artist) creates a Submission row. All entities created in that submission reference it via `submission_id`. This grouping key allows the Submissions page to display, approve, or reject an entire submission as a unit.
- **Approval:** Approval status is derived from the Submission, not stored on individual entities. Every entity has a `submission_id` (NOT NULL). An entity is approved if its referenced Submission has `status = 'approved'`; pending if `status = 'pending'`. Legacy/seed data references the seed Submission (id=0, `status = 'approved'`). When an editor approves a submission, application code sets the Submission to `status = 'approved'` with `approved_by_id` and `approved_at`. Any songs the editor marked for rejection during review are deleted (along with their ratings), and a changelog entry is created for each. Editor and Admin submissions are auto-approved (Submission `status = 'approved'`, `approved_by_id = 0`).
- **Rejection (full submission):** On full rejection, application code deletes all entities created by the submission (artist, albums, songs, ratings). Changelog entries referencing these items survive with NULL foreign keys (via ON DELETE SET NULL). A new changelog entry is created recording the rejection. The Submission row is updated with `status = 'rejected'`, `rejected_by_id`, `rejected_at`, and `rejected_reason` — the Submission row itself is never deleted.
- **User deletion:** Application code must perform the following steps in order:
    1. Rename the user's personal theme: set `Themes.name = 'deleted_' + username` for the theme row where `user_id` matches the user being deleted.
    2. Delete the User row. This cascades to: Ratings (ON DELETE CASCADE), User_Settings (ON DELETE CASCADE). It sets NULL on: `submitted_by_id` columns (Artists, Albums, Songs, Submissions), `user_id`/`approved_by_id` (Changelog), `user_id` (Themes), `approved_by_id`/`rejected_by_id` (Submissions).
    3. Compact `sort_order`: within the same transaction (after the DELETE has freed the old value), decrement `sort_order` by 1 for all users whose `sort_order` was greater than the deleted user's value, ordered by `sort_order ASC`. This closes the gap and keeps `sort_order` contiguous. The UNIQUE constraint is not violated because the DELETE runs first (freeing the gap) and the UPDATE processes rows in ascending order (each row moves into the slot just vacated by the previous update).
    4. All submitted content (Artists, Albums, Songs, Changelog entries) survives the deletion.

## Frontend Implementation Notes

- Every colour in the app is loaded from the user's selected theme (stored in the Themes table). No hardcoded colours — all colours are injected as CSS custom properties from the theme row on page load. For any NULL column in the selected theme, the Classic (id=0) theme colour is used as fallback.
- Classic and Dark Mode are standalone themes (no automatic toggle). Users select a theme explicitly on their Profile page.
- **Unapproved items are always visible.** Pending (unapproved) artists, albums, and songs appear on all pages alongside approved content. An item is pending if its referenced Submission has `status = 'pending'`. Pending items are visually distinguished using theme-driven styling (e.g., reduced opacity, different background colour, or a "pending" badge). Users can interact with pending items (including rating pending songs). Pending items display a link to the Submissions page so editors/admins can navigate directly to approve or edit them. All queries that display content (Artists, Global Stats, Artist Stats) include unapproved items — there is no approval filter on read queries.

## In Progress / Open Questions

- When creating an album and selecting a song, typing in the field should show existing options as a dropdown. Pressing Enter creates a new entry.
- When leaving an edit page, prompt the user to check for capitalisation and other changes.
- **Subunit & soloist display rules** are defined in the table below. Application code traverses `Artist_Artist` to find child artists and unions their songs into the parent's data where specified.
    - When searching artists, searching for a subunit should bring up the main artist page.

### Subunit & Soloist Display Rules

| Context                                           | Subunit                                                                 | Soloist                                                                                     |
|---------------------------------------------------|-------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| **Artist Stats — top table** (summary rows)       | Nested under parent (expandable ">" row), own stats shown when expanded | Own standalone row                                                                          |
| **Artist Stats — bottom table** (per-artist rows) | Nested under parent (expandable ">" row), own stats shown when expanded | Own standalone row                                                                          |
| **Global Stats** (per-artist rows)                | Nested under parent (expandable ">" row), own stats shown when expanded | Own standalone row                                                                          |
| **Artists — bottom navbar**                       | Not listed (accessed only via parent)                                   | Own entry                                                                                   |
| **Artists — parent's discography page**           | Songs appear under parent's discography                                 | Songs appear under parent's discography (for browsing only — not counted in parent's stats) |
| **Artists — own discography page**                | No own page                                                             | Own page                                                                                    |
| **Scored group denominator**                      | Songs counted in parent's total                                         | Songs NOT counted in parent's total                                                         |
| **Stats calculations (parent row)**               | Subunit songs included in parent's averages                             | Soloist songs excluded from parent's averages                                               |
| **Stats calculations (expanded row)**             | Subunit shows its own independent averages                              | N/A (soloist has own standalone row)                                                        |

**Nesting depth:** Subunits cannot have their own subunits. A member of a subunit who goes solo is a soloist of the parent artist, not of the subunit. All Artist_Artist relationships are exactly one level deep.
- Need a way to see a list of artists by last updated date (excluding disbanded artists), with a button to mark as up to date. (Custom page?)
- If an externally-facing API is offered, it would have User-level permissions, not Editor or Admin.
- Would like to add Spotify and Last.fm links to the Songs table for future integrations, but not for v1.
- [v2] **Duplicate song filtering:** Songs that appear on multiple albums (e.g., original release and repackage) are currently shown under every album. In v2, implement the `hide_duplicate_songs` user setting to allow users to show each song only once (under the earliest album by release date). The column already exists in User_Settings as scaffolding.
