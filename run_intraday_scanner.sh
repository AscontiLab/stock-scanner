#!/bin/bash
# CFD Intraday Scanner — Wrapper-Script (alle 15 min via systemd timer).

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCK_FILE="/tmp/stock_scanner_intraday.lock"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/intraday_$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "$(date '+%Y-%m-%d %H:%M:%S') Intraday-Scanner laeuft bereits — Abbruch." >> "$LOG_FILE"
    exit 0
fi

cd "$SCRIPT_DIR" || exit 1

echo "--- Start $(date '+%Y-%m-%d %H:%M:%S') ---" >> "$LOG_FILE"
/usr/bin/python3 cfd_intraday_scanner.py "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?
echo "--- Ende  $(date '+%Y-%m-%d %H:%M:%S')  (Exit: $EXIT_CODE) ---" >> "$LOG_FILE"

# Logs aelter als 14 Tage loeschen
find "$LOG_DIR" -name "intraday_*.log" -mtime +14 -delete

exit $EXIT_CODE
