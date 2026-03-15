#!/usr/bin/env bash
# Auto-Resolve: Loest offene CFD-Signale auf und prueft Portfolio.
# Cron: 0 23 * * 1-5 (Mo-Fr, 23:00 UTC, 30min nach Scanner)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

DATE=$(date +%Y-%m-%d)
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/resolve_${DATE}.log"

echo "=== Auto-Resolve gestartet: $(date) ===" | tee -a "$LOG_FILE"

# 1. Backtesting resolve
echo "--- Backtesting Resolve ---" | tee -a "$LOG_FILE"
python3 cfd_backtesting.py resolve 2>&1 | tee -a "$LOG_FILE"

# 2. Portfolio check (prueft Stop/TP)
echo "--- Portfolio Check ---" | tee -a "$LOG_FILE"
python3 cfd_portfolio.py check 2>&1 | tee -a "$LOG_FILE"

# 3. Dashboard-Daten an n8n pushen (Portfolio + Backtesting)
echo "--- Dashboard Update ---" | tee -a "$LOG_FILE"
python3 write_dashboard_data.py 2>&1 | tee -a "$LOG_FILE"

# 4. Telegram Summary
python3 -c "
from datetime import date
from telegram_alerts import send_message
from cfd_portfolio import list_positions
positions = list_positions()
import sqlite3
from pathlib import Path
today = date.today().isoformat()
db = Path('cfd_backtesting.db')
resolved_today = 0
if db.exists():
    with sqlite3.connect(str(db)) as conn:
        cur = conn.cursor()
        cur.execute('SELECT COUNT(*) FROM cfd_signals WHERE resolved_at LIKE ?', (today + '%',))
        resolved_today = cur.fetchone()[0]
msg = f'Auto-Resolve {today}\nAufgeloest heute: {resolved_today}\nAktive Positionen: {len(positions)}'
send_message(msg)
print(msg)
" 2>&1 | tee -a "$LOG_FILE"

echo "=== Auto-Resolve beendet: $(date) ===" | tee -a "$LOG_FILE"
