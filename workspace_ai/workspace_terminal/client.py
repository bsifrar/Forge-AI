from __future__ import annotations

import json
from typing import Any, Dict, Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class APIClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8092") -> None:
        self.base_url = base_url.rstrip("/")

    def get(self, path: str, params: Dict[str, Any] | None = None) -> Dict[str, Any]:
        query = f"?{urlencode(params or {})}" if params else ""
        return self._send(Request(f"{self.base_url}{path}{query}", method="GET"))

    def post(self, path: str, payload: Dict[str, Any] | None = None) -> Dict[str, Any]:
        return self._send(Request(f"{self.base_url}{path}", data=json.dumps(payload or {}).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST"))

    def post_stream(self, path: str, payload: Dict[str, Any] | None = None) -> Iterable[Dict[str, Any]]:
        request = Request(f"{self.base_url}{path}", data=json.dumps(payload or {}).encode("utf-8"), headers={"Content-Type": "application/json", "Accept": "text/event-stream"}, method="POST")
        try:
            with urlopen(request, timeout=300) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8", errors="replace").strip()
                    if line.startswith("data:"):
                        yield json.loads(line[5:].strip())
        except HTTPError as exc:
            yield {"type": "workspace.error", "code": exc.code, "detail": exc.read().decode("utf-8", errors="replace")}
        except URLError as exc:
            yield {"type": "workspace.error", "detail": str(exc)}

    def _send(self, request: Request) -> Dict[str, Any]:
        try:
            with urlopen(request, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            return {"status": "error", "code": exc.code, "detail": exc.read().decode("utf-8", errors="replace")}
        except URLError as exc:
            return {"status": "error", "detail": str(exc)}
