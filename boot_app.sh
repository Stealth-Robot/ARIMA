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

# Load env vars from .env file
if [ -f .env ]; then
    set -a
    . .env
    set +a
fi
export FLASK_APP=app:create_app

# Seed database (idempotent — always run to pick up theme/lookup changes)
echo "Seeding database..."
flask seed

echo ""
echo "==================================="
echo "  ARIMA running on http://127.0.0.1:5000"
echo "  Login: Stealth / admin"
echo "  Or click 'Login as Guest'"
echo "==================================="
echo ""
flask run --debug
