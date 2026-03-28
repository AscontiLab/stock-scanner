"""Hilfsskript: Investment-Portfolio-Check als JSON auf stdout.

Wird vom Unified Dashboard per subprocess aufgerufen, um sys.path-Konflikte zu vermeiden.
Alle Debug-Ausgaben gehen auf stderr, nur das JSON-Ergebnis auf stdout.
"""
import csv
import json
import sys

# Debug-Ausgaben auf stderr umleiten
_print = print
def print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _print(*args, **kwargs)

from investment_portfolio import list_stocks, check_stocks

stocks = list_stocks()
rows = []
try:
    with open("all_results.csv", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
except FileNotFoundError:
    pass

reports = check_stocks(stocks, rows) if stocks else []
_print(json.dumps(reports), file=sys.stdout)
