# A.R.I.M.A.

**A**pp for **R**ating and **I**ndexing **M**usic **A**lbums

A lightweight web app for a small group of friends to rate music together. Browse artists, albums, and songs, rate tracks on a 0-5 scale, and compare scores across the group with aggregate stats and rankings.

## Tech Stack

- **Backend:** Flask, SQLAlchemy, SQLite
- **Frontend:** Jinja2 templates, HTMX, Tailwind CSS (vendored locally)
- **Auth:** Flask-Login, bcrypt with server-side pepper
- **Hosting:** Railway (with persistent volume for SQLite)

## Local Setup

### Prerequisites

- Python 3.12+
- Git

### Installation

```bash
git clone https://github.com/Stealth-Robot/ARIMA.git
cd ARIMA

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

### Configuration

Copy the example environment file and fill in your values:

```bash
cp .env.example .env
```

Required variables:
- `SECRET_KEY` — random 64-char hex string (e.g. `python3 -c "import secrets; print(secrets.token_hex(32))"`)
- `PEPPER` — random 32-char hex string

### Database Setup

```bash
flask seed
```

This creates all tables and inserts seed data (roles, system users, default themes). The seed is idempotent and safe to re-run.

### Running

```bash
flask run
```

The app will be available at `http://localhost:5000`. Log in with the default admin account (`Stealth` / `admin`).

## Project Structure

```
ARIMA/
├── app/
│   ├── __init__.py          # create_app() factory
│   ├── config.py            # Config classes (Dev, Prod)
│   ├── extensions.py        # db, login_manager, bcrypt, csrf
│   ├── models/              # SQLAlchemy models
│   ├── routes/              # Route modules (blueprints)
│   ├── services/            # Business logic
│   ├── templates/           # Jinja2 templates
│   │   └── fragments/       # HTMX partials
│   └── static/              # CSS, JS, images
├── scripts/                 # Data import/export scripts
├── migrations/              # One-off schema migration scripts
├── .env.example
├── requirements.txt
├── Procfile                 # Railway: gunicorn
└── runtime.txt              # Python version
```

## License

MIT — see [LICENSE](LICENSE).
