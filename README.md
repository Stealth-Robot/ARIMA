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

### Quick Start

```bash
git clone https://github.com/Stealth-Robot/ARIMA.git
cd ARIMA
cp .env.example .env
```

Edit `.env` and set the two required variables:

```
SECRET_KEY=<random 64-char hex string>
PEPPER=<ask the project owner>
```

- `SECRET_KEY` — generate your own: `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `PEPPER` — get this from the project owner. Passwords are hashed with the pepper, so you need the same value to log in with a copy of the production database.

Then run the boot script, which creates the venv, installs dependencies, seeds the database, and starts the dev server:

```bash
./boot_app.sh
```

The app will be available at `http://127.0.0.1:5000`. Log in with the default admin account (`Stealth` / `admin`), or click "Login as Guest" for read-only access.

> **Note:** If you import the production database, you will need to change the Stealth user's password back to `admin` BEFORE logging out or closing the app in terminal, otherwise you will be unable to log in.

### Manual Setup

If you prefer to set up step by step:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=app:create_app
flask seed        # create tables + seed data (idempotent)
flask run --debug
```

### Optional Configuration

The following `.env` variables are optional and only needed for specific features:

| Variable | Purpose |
|----------|---------|
| `RESEND_API_KEY` | Send invite emails via [Resend](https://resend.com) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` | Send invite emails via SMTP instead of Resend |
| `SMTP_FROM`, `SMTP_FROM_NAME` | Sender address and display name for emails |
| `FLASK_ENV` | Set to `production` for deployed environments |
| `APP_URL` | Production URL used in email links |

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
