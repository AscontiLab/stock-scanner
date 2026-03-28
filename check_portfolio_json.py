"""Hilfsskript: CFD-Portfolio-Check als JSON auf stdout.

Wird vom Unified Dashboard per subprocess aufgerufen, um sys.path-Konflikte zu vermeiden.
Alle Debug-Ausgaben gehen auf stderr, nur das JSON-Ergebnis auf stdout.
"""
import json
import sys

_print = print
def print(*args, **kwargs):
    kwargs.setdefault("file", sys.stderr)
    _print(*args, **kwargs)

from cfd_portfolio import list_positions, check_positions

pos = list_positions()
reports = check_positions(pos) if pos else []
_print(json.dumps(reports), file=sys.stdout)
