#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

# Install deps
pip install -q -r requirements.txt

# Dev env vars (override with real values in production)
export SECRET_KEY="${SECRET_KEY:-dev-secret-key-change-me}"
export PEPPER="${PEPPER:-dev-pepper-change-me}"
export FLASK_APP=app:create_app

# Seed database if it doesn't exist
if [ ! -f "instance/arima.db" ]; then
    echo "Seeding database..."
    flask seed
    # Import spreadsheet data if data.json exists
    if [ -f "data.json" ]; then
        echo "Importing spreadsheet data..."
        flask import-data data.json
    fi
fi

# Set admin password if not already set
python3 -c "
from app import create_app
from app.extensions import db
from app.models.user import User
from app.routes.auth import _hash_password

app = create_app()
with app.app_context():
    admin = db.session.get(User, 2)
    if admin:
        admin.password = _hash_password('admin')
        db.session.commit()
        print('Admin password set to: admin')
"

echo ""
echo "==================================="
echo "  ARIMA running on http://127.0.0.1:5000"
echo "  Login: Stealth_Robot / admin"
echo "  Or click 'Login as Guest'"
echo "==================================="
echo ""
flask run
