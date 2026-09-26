"""Tests for health.py — method matrix over an ephemeral local port."""
from __future__ import annotations

import http.client

from health import serve_in_background


def _call(port: int, method: str):
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request(method, "/health")
        return conn.getresponse()
    finally:
        conn.close()


def test_health_method_matrix():
    server = serve_in_background(0, host="127.0.0.1")
    port = server.server_address[1]
    try:
        # GET -> 200 "OK" with cache + content headers.
        response = _call(port, "GET")
        assert response.status == 200
        assert response.read() == b"OK"
        assert response.getheader("Content-Type") == "text/plain; charset=utf-8"
        assert response.getheader("Content-Length") == "2"
        assert response.getheader("Cache-Control") == "no-store"

        # HEAD -> 200, same Content-Length as GET, but no body.
        response = _call(port, "HEAD")
        assert response.status == 200
        assert response.read() == b""
        assert response.getheader("Content-Length") == "2"
        assert response.getheader("Cache-Control") == "no-store"

        # OPTIONS -> 204 with Allow.
        response = _call(port, "OPTIONS")
        assert response.status == 204
        assert response.getheader("Allow") == "GET, HEAD, OPTIONS"
        assert response.read() == b""
    finally:
        server.shutdown()
        server.server_close()
