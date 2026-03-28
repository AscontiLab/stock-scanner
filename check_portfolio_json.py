"""Hilfsskript: CFD-Portfolio-Check als JSON auf stdout.

Wird vom Unified Dashboard per subprocess aufgerufen.
Alle Print-Ausgaben werden auf stderr umgeleitet, nur JSON auf stdout.
"""
import json
import os
import sys

# stdout auf stderr umleiten BEVOR irgendein Import passiert
_real_stdout = os.fdopen(os.dup(1), "w")
os.dup2(sys.stderr.fileno(), 1)

from cfd_portfolio import list_positions, check_positions

pos = list_positions()
reports = check_positions(pos) if pos else []

# JSON auf den echten stdout schreiben
_real_stdout.write(json.dumps(reports))
_real_stdout.write("\n")
_real_stdout.close()
