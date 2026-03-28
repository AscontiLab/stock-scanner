"""Hilfsskript: Investment-Portfolio-Check als JSON auf stdout.

Wird vom Unified Dashboard per subprocess aufgerufen.
Alle Print-Ausgaben werden auf stderr umgeleitet, nur JSON auf stdout.
"""
import csv
import json
import os
import sys

# stdout auf stderr umleiten BEVOR irgendein Import passiert
_real_stdout = os.fdopen(os.dup(1), "w")
os.dup2(sys.stderr.fileno(), 1)

from investment_portfolio import list_stocks, check_stocks

stocks = list_stocks()
rows = []
try:
    with open("all_results.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
except FileNotFoundError:
    pass

reports = check_stocks(stocks, rows) if stocks else []

# JSON auf den echten stdout schreiben
_real_stdout.write(json.dumps(reports))
_real_stdout.write("\n")
_real_stdout.close()
