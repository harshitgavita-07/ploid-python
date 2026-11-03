"""Zero-dependency HTTP transport for the Ploid API.

- Auth via ``Authorization: Bearer <key>`` (default) or ``x-api-key``.
- 429s are retried honoring ``Retry-After``; 5xx retried with exponential
  backoff + jitter. 401/402/403/404/409/410/413/422 are never retried.
- ``Idempotency-Key`` is auto-generated for POST/PATCH when not supplied,
  and stays stable across internal retries of the same call.
"""
from __future__ import annotations

import json
import time
import uuid
import random
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from .errors import APIError, TransportError, error_from_response

DEFAULT_BASE_URL = "https://api.ploid.com"
USER_AGENT = "ploid-python/0.1.0 (+https://github.com/harshitgavita-07/ploid-python)"
_NO_RETRY = {400, 401, 402, 403, 404, 409, 410, 413, 422}


class HttpClient:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = DEFAULT_BASE_URL,
        auth_scheme: str = "bearer",  # or "x-api-key"
        timeout: float = 30.0,
        max_retries: int = 3,
        sleep=time.sleep,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        if auth_scheme not in ("bearer", "x-api-key"):
            raise ValueError("auth_scheme must be 'bearer' or 'x-api-key'")
        self.auth_scheme = auth_scheme
        self.timeout = timeout
        self.max_retries = max_retries
        self._sleep = sleep  # injectable for tests

    def _auth_headers(self) -> Dict[str, str]:
        if self.auth_scheme == "x-api-key":
            return {"x-api-key": self.api_key}
        return {"Authorization": f"Bearer {self.api_key}"}

    def request(
        self,
        method: str,
        path: str,
        *,
        query: Optional[Dict[str, Any]] = None,
        body: Any = None,
        idempotency_key: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Tuple[int, Dict[str, str], Any]:
        """Perform one logical request (with internal retries).

        Returns ``(status, headers, parsed_body)``. Raises APIError subclasses
        for non-2xx responses after retries are exhausted.
        """
        url = self.base_url + path
        if query:
            clean = {k: v for k, v in query.items() if v is not None}
            if clean:
                url += "?" + urllib.parse.urlencode(clean, doseq=True)

        data = None
        base_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            **self._auth_headers(),
        }
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            base_headers["Content-Type"] = "application/json"
        if method in ("POST", "PATCH"):
            base_headers["Idempotency-Key"] = idempotency_key or str(uuid.uuid4())
        if headers:
            base_headers.update(headers)

        attempt = 0
        while True:
            req = urllib.request.Request(url, data=data, headers=base_headers, method=method)
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    raw = resp.read().decode("utf-8", "replace")
                    return resp.status, dict(resp.headers), _parse(raw)
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8", "replace") if e.fp else ""
                parsed = _parse(raw)
                retry_after = _retry_after(e.headers)
                if e.code in _NO_RETRY or attempt >= self.max_retries:
                    raise error_from_response(e.code, parsed, retry_after)
                delay = self._delay(attempt, e.code, retry_after)
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                if attempt >= self.max_retries:
                    raise TransportError(f"request to {url} failed: {e}") from e
                delay = self._delay(attempt, None, None)
            self._sleep(delay)
            attempt += 1

    def _delay(self, attempt: int, status: Optional[int], retry_after: Optional[float]) -> float:
        if status == 429 and retry_after is not None:
            return min(float(retry_after), 60.0)
        return min(0.5 * (2 ** attempt), 8.0) + random.uniform(0, 0.25)


def _parse(raw: str) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}


def _retry_after(headers: Any) -> Optional[float]:
    if not headers:
        return None
    value = headers.get("Retry-After")
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
