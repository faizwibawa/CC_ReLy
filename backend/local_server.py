"""Run the ReLy Lambda handler locally with an in-memory store (no AWS needed).

Useful for developing the dashboard and simulator offline:
    python backend/local_server.py            # serves http://127.0.0.1:8787
    RELY_API_URL=http://127.0.0.1:8787 python simulator/simulator.py

It converts each HTTP request into a Lambda Function URL event (payload 2.0), so the
exact same handler code runs locally and in AWS. Data is lost when the server stops.
"""
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qsl, urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import handler  # noqa: E402
from repository import InMemorySignalRepository  # noqa: E402

handler.set_repo(InMemorySignalRepository())
PORT = int(os.environ.get("PORT", "8787"))


class Proxy(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE")
        self.send_header("Access-Control-Allow-Headers", "content-type")

    def do_OPTIONS(self):  # CORS preflight (AWS Function URLs handle this automatically)
        self.send_response(204)
        self._cors()
        self.end_headers()

    def _handle(self):
        url = urlsplit(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode() if length else None
        event = {
            "rawPath": url.path,
            "queryStringParameters": dict(parse_qsl(url.query)) or None,
            "requestContext": {"http": {"method": self.command, "path": url.path}},
            "body": body,
            "isBase64Encoded": False,
        }
        result = handler.lambda_handler(event, None)
        payload = (result.get("body") or "").encode()
        self.send_response(result["statusCode"])
        for key, val in result.get("headers", {}).items():
            self.send_header(key, val)
        self._cors()
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_PUT = do_DELETE = _handle

    def log_message(self, *_):  # the handler already logs each request as JSON
        pass


if __name__ == "__main__":
    print(f"ReLy local API on http://127.0.0.1:{PORT}  (in-memory, SIMULATED data)")
    ThreadingHTTPServer(("127.0.0.1", PORT), Proxy).serve_forever()
