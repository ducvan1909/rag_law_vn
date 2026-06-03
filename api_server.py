import json
import os
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from dotenv import load_dotenv

from rag.generation import generate_answer, load_generation_model

ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(ROOT_DIR / ".env")

HOST = os.getenv("CHAT_API_HOST", "0.0.0.0")
PORT = int(os.getenv("CHAT_API_PORT", "8000"))

MODEL = load_generation_model()


class ChatHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A003
        return

    def _set_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS, GET")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _write_json(self, status_code, payload):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self._set_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(HTTPStatus.NO_CONTENT)
        self._set_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self.path == "/health":
            self._write_json(HTTPStatus.OK, {"status": "ok"})
            return

        self._write_json(
            HTTPStatus.NOT_FOUND,
            {"message": "Not found"},
        )

    def do_POST(self):
        if self.path != "/chat":
            self._write_json(
                HTTPStatus.NOT_FOUND,
                {"message": "Not found"},
            )
            return

        content_length = int(self.headers.get("Content-Length", "0") or "0")
        raw_body = self.rfile.read(content_length) if content_length > 0 else b"{}"

        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except json.JSONDecodeError:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"message": "Request body must be valid JSON."},
            )
            return

        question = (payload.get("question") or "").strip()
        if not question:
            self._write_json(
                HTTPStatus.BAD_REQUEST,
                {"message": "Missing question."},
            )
            return

        try:
            answer = generate_answer(model=MODEL, query=question)
        except Exception as exc:  # pragma: no cover - surfaced through API
            self._write_json(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"message": str(exc)},
            )
            return

        self._write_json(
            HTTPStatus.OK,
            {"answer": answer},
        )


def main():
    server = ThreadingHTTPServer((HOST, PORT), ChatHandler)
    print(f"Chat API listening on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
