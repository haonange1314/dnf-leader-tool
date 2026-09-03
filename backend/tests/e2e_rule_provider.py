"""Deterministic DeepSeek-compatible HTTP fixture for isolated browser acceptance."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path != "/health":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._json_response({"status": "ok"})

    def do_POST(self) -> None:
        if self.path != "/chat/completions":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(content_length))
            user_message = json.loads(body["messages"][1]["content"])
            source_text = str(user_message["sourceText"])
            participants = user_message["context"]["participants"]
            player_name = next(
                str(item["playerName"])
                for item in participants
                if str(item["playerName"]) in source_text
            )
        except (KeyError, StopIteration, TypeError, ValueError, json.JSONDecodeError):
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        provider_output = {
            "schemaVersion": 1,
            "rules": [
                {
                    "candidateId": "E2E-R1",
                    "type": "PLAYER_ALLOWED_WAVES",
                    "enforcement": "HARD",
                    "playerReference": {"text": player_name},
                    "waves": [1],
                    "explanation": f"{player_name} 仅参加第 1 波",
                }
            ],
            "unsupportedItems": [],
        }
        self._json_response(
            {
                "id": "e2e-rule-response",
                "model": "deepseek-e2e-fixture",
                "choices": [
                    {"message": {"content": json.dumps(provider_output, ensure_ascii=False)}}
                ],
            }
        )

    def log_message(self, _format: str, *_args: Any) -> None:
        return

    def _json_response(self, body: dict[str, Any]) -> None:
        payload = json.dumps(body, ensure_ascii=False).encode()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 18080), Handler).serve_forever()
