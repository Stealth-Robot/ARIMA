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
fi

echo "Starting ARIMA on http://127.0.0.1:5000"
flask run
