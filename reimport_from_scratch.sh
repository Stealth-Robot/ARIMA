#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

source venv/bin/activate

export SECRET_KEY="${SECRET_KEY:-dev-secret-key-change-me}"
export PEPPER="${PEPPER:-dev-pepper-change-me}"
export FLASK_APP=app:create_app

echo "Exporting spreadsheet..."
venv/bin/python scripts/export_spreadsheet.py "lettuce kpop.xlsx" --output data.json

echo "Deleting database..."
rm -f instance/arima.db instance/.imported

echo "Seeding database..."
flask seed

echo "Importing data..."
flask import-data data.json

touch instance/.imported

echo ""
echo "==================================="
echo "  Reimport complete."
echo "==================================="
