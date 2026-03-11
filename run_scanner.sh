#!/bin/bash
# Daily Stock Scanner — Wrapper-Script
# Läuft täglich Mo–Fr nach US-Börsenschluss (via cron)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
LOG_FILE="$LOG_DIR/scanner_$(date +%Y-%m-%d).log"

mkdir -p "$LOG_DIR"

echo "======================================" >> "$LOG_FILE"
echo "Start: $(date '+%Y-%m-%d %H:%M:%S')"  >> "$LOG_FILE"
echo "======================================" >> "$LOG_FILE"

cd "$SCRIPT_DIR" || exit 1

/usr/bin/python3 stock_scanner.py >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

echo "Ende: $(date '+%Y-%m-%d %H:%M:%S')  (Exit: $EXIT_CODE)" >> "$LOG_FILE"

# Dashboard Push + E-Mail-Report
if [ $EXIT_CODE -eq 0 ]; then
    # Dashboard-Push (stock_scanner.py macht das bereits intern — nur Fallback)
    # echo "Pushe Dashboard-Daten ..." >> "$LOG_FILE"
    # /usr/bin/python3 "$SCRIPT_DIR/post_to_dashboard.py" >> "$LOG_FILE" 2>&1

    echo "Sende E-Mail-Report ..." >> "$LOG_FILE"
    /usr/bin/python3 "$SCRIPT_DIR/send_report.py" >> "$LOG_FILE" 2>&1
    if [ $? -eq 0 ]; then
        echo "E-Mail erfolgreich gesendet." >> "$LOG_FILE"
    else
        echo "FEHLER: E-Mail konnte nicht gesendet werden." >> "$LOG_FILE"
    fi
else
    echo "Scanner fehlgeschlagen — kein E-Mail-Versand." >> "$LOG_FILE"
fi

# Logs älter als 30 Tage löschen
find "$LOG_DIR" -name "scanner_*.log" -mtime +30 -delete

exit $EXIT_CODE
