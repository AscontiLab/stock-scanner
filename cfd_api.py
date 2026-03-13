#!/usr/bin/env python3
"""
Minimaler HTTP-API-Server für das CFD-Portfolio.
Läuft auf dem Host und wird von n8n per HTTP Request angesprochen.

Endpoints:
    POST /api/cfd/add       {ticker, direction}
    POST /api/cfd/close     {ticker}
    GET  /api/cfd/positions
    GET  /api/cfd/check
"""

import json
import os
import secrets
from http.server import HTTPServer, BaseHTTPRequestHandler

from cfd_portfolio import (
    add_position, close_position, list_positions, check_positions,
)

PORT = 5051
MAX_CONTENT_LENGTH = 1_048_576  # 1 MB Max-Request-Groesse

# API-Key aus Umgebungsvariable oder zufaellig generiert
API_KEY = os.environ.get("CFD_API_KEY") or secrets.token_urlsafe(32)


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, data: dict, code: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "http://localhost")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def _check_auth(self) -> bool:
        """Prueft API-Key im Header X-API-Key."""
        key = self.headers.get("X-API-Key", "")
        if not secrets.compare_digest(key, API_KEY):
            self._send_json({"error": "Unauthorized"}, 401)
            return False
        return True

    def do_OPTIONS(self):
        """CORS Preflight."""
        self._send_json({})

    def do_GET(self):
        if not self._check_auth():
            return
        if self.path == "/api/cfd/positions":
            positions = list_positions()
            self._send_json({"ok": True, "positions": positions})
        elif self.path == "/api/cfd/check":
            reports = check_positions()
            self._send_json({"ok": True, "reports": reports})
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self):
        if not self._check_auth():
            return
        length = int(self.headers.get("Content-Length", 0))
        if length > MAX_CONTENT_LENGTH:
            self._send_json({"error": "Request zu gross (max 1 MB)"}, 413)
            return
        body = json.loads(self.rfile.read(length)) if length else {}

        if self.path == "/api/cfd/add":
            ticker = body.get("ticker", "").upper()
            direction = body.get("direction", "").lower()
            if not ticker or direction not in ("long", "short"):
                self._send_json({"error": "ticker und direction (long/short) erforderlich"}, 400)
                return
            try:
                pos = add_position(ticker, direction)
                self._send_json({"ok": True, "position": pos})
            except Exception as e:
                self._send_json({"error": str(e)}, 500)

        elif self.path == "/api/cfd/close":
            ticker = body.get("ticker", "").upper()
            if not ticker:
                self._send_json({"error": "ticker erforderlich"}, 400)
                return
            closed = close_position(ticker)
            self._send_json({"ok": True, "closed": closed})

        else:
            self._send_json({"error": "Not found"}, 404)

    def log_message(self, format, *args):
        """Nur Fehler loggen."""
        if args and "200" not in str(args[1]):
            super().log_message(format, *args)


if __name__ == "__main__":
    if not os.environ.get("CFD_API_KEY"):
        print(f"Kein CFD_API_KEY gesetzt, verwende generierten Key: {API_KEY}")
    print(f"CFD Portfolio API laeuft auf http://127.0.0.1:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
