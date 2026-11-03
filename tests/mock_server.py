"""Threaded mock Ploid API server for tests."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs


class MockPloid:
    """Scripted responses: list of (method, path_prefix, status, body, headers)."""

    def __init__(self):
        self.routes = []
        self.requests = []  # recorded: (method, path, query, headers, body)

    def add(self, method, path_prefix, status=200, body=None, headers=None):
        self.routes.append((method, path_prefix, status, body if body is not None else {}, headers or {}))

    def __enter__(self):
        mock = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _handle(self):
                parsed = urlparse(self.path)
                length = int(self.headers.get("Content-Length") or 0)
                raw = self.rfile.read(length).decode() if length else ""
                try:
                    body = json.loads(raw) if raw else None
                except json.JSONDecodeError:
                    body = raw
                mock.requests.append((self.command, parsed.path,
                                      parse_qs(parsed.query),
                                      {k.lower(): v for k, v in self.headers.items()}, body))
                for i, (method, prefix, status, resp_body, extra) in enumerate(mock.routes):
                    if self.command == method and parsed.path.startswith(prefix):
                        del mock.routes[i]
                        payload = json.dumps(resp_body).encode()
                        self.send_response(status)
                        self.send_header("Content-Type", "application/json")
                        for k, v in extra.items():
                            self.send_header(k, v)
                        self.send_header("Content-Length", str(len(payload)))
                        self.end_headers()
                        self.wfile.write(payload)
                        return
                payload = json.dumps({"error": {"code": "not_mocked",
                                                "message": f"no route for {self.command} {parsed.path}",
                                                "request_id": "req_mock"}}).encode()
                self.send_response(599)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = do_PATCH = do_DELETE = do_PUT = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.port}"
        return self

    def __exit__(self, *a):
        self.server.shutdown()
        self.server.server_close()


def api_error(code, message, request_id="req_test", **extra):
    err = {"code": code, "message": message, "request_id": request_id}
    err.update(extra)
    return {"error": err}
