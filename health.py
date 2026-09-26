"""Hardened HTTP health server for the Render web service.

Supports GET/HEAD/OPTIONS, returns ``OK`` with correct headers, and runs on a
``ThreadingHTTPServer`` so concurrent keep-alive pings never block.
"""
from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

logger = logging.getLogger(__name__)

_OK_BODY = b"OK"


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "PollBotHealth/1.0"
    timeout = 10

    def _write_headers(self, status: int, *, body_length: int, content_type: bool = True) -> None:
        self.send_response(status)
        if content_type:
            self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(body_length))
        self.send_header("Cache-Control", "no-store")
        if status == 204:
            self.send_header("Allow", "GET, HEAD, OPTIONS")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 (http.server API)
        self._write_headers(200, body_length=len(_OK_BODY))
        self.wfile.write(_OK_BODY)

    def do_HEAD(self) -> None:  # noqa: N802
        # Same headers as GET, but no body.
        self._write_headers(200, body_length=len(_OK_BODY))

    def do_OPTIONS(self) -> None:  # noqa: N802
        self._write_headers(204, body_length=0, content_type=False)

    def log_message(self, format: str, *args: object) -> None:
        logger.debug("%s - %s", self.address_string(), format % args)


def serve_in_background(port: int, host: str = "0.0.0.0") -> ThreadingHTTPServer:
    """Bind *port* synchronously, then serve forever on a daemon thread.

    Binding happens before the thread starts, so errors (e.g. port in use)
    propagate to the caller. Pass ``port=0`` to bind an ephemeral port and read
    it back from ``server.server_address[1]``.
    """
    server = ThreadingHTTPServer((host, port), HealthHandler)
    server.daemon_threads = True
    thread = threading.Thread(
        target=server.serve_forever,
        name="health-server",
        daemon=True,
    )
    thread.start()
    logger.info("Health server listening on %s:%d", host, port)
    return server
