#!/bin/bash
# ─── NiftyEdge Pro — Startup Script ──────────────────────────────────────────
# Usage: bash start.sh

set -e
cd "$(dirname "$0")"

echo ""
echo "  ⚡ NiftyEdge Pro — Dhan Options Trading Dashboard"
echo "  ─────────────────────────────────────────────────"
echo ""

# Load .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
  echo "  ✅ Loaded .env"
else
  echo "  ⚠️  No .env file found. Copy .env and fill in your Dhan credentials."
  exit 1
fi

# Check credentials
if [ "$DHAN_CLIENT_ID" = "YOUR_CLIENT_ID_HERE" ] || [ "$DHAN_ACCESS_TOKEN" = "YOUR_ACCESS_TOKEN_HERE" ]; then
  echo ""
  echo "  ❌ ERROR: Please set your DHAN_CLIENT_ID and DHAN_ACCESS_TOKEN in .env"
  echo "     Get them from: https://api.dhan.co → My Apps → Create App"
  echo ""
  exit 1
fi

# Install dependencies
echo "  📦 Installing Python dependencies..."
pip install -r requirements.txt --quiet

echo ""
echo "  🚀 Starting server on http://0.0.0.0:5000"
echo "  📈 Open http://localhost:5000 in your browser"
echo "  🛑 Press Ctrl+C to stop"
echo ""

python app.py
