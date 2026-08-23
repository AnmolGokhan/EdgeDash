from types import SimpleNamespace

import pytest
import requests

from edgedash.sources import http


def _http_error(status: int) -> requests.exceptions.HTTPError:
    response = SimpleNamespace(status_code=status)
    error = requests.exceptions.HTTPError(f"HTTP {status}")
    error.response = response
    return error


def test_get_json_retries_429_with_exponential_backoff(monkeypatch):
    calls = []
    sleeps = []

    class Response:
        def __init__(self, error=None):
            self.error = error

        def raise_for_status(self):
            if self.error:
                raise self.error

        def json(self):
            return {"ok": True}

    responses = [Response(_http_error(429)), Response(_http_error(429)), Response()]
    monkeypatch.setattr(http.requests, "get", lambda *args, **kwargs: calls.append(kwargs) or responses.pop(0))
    monkeypatch.setattr(http.time, "sleep", sleeps.append)

    assert http.get_json("https://example.test") == {"ok": True}
    assert len(calls) == 3
    assert sleeps == [1.0, 2.0]


def test_get_json_stops_after_bounded_429_retries(monkeypatch):
    sleeps = []
    monkeypatch.setattr(http.requests, "get", lambda *args, **kwargs: type("Response", (), {"raise_for_status": lambda self: (_ for _ in ()).throw(_http_error(429))})())
    monkeypatch.setattr(http.time, "sleep", sleeps.append)

    with pytest.raises(http.SourceError, match="HTTP 429"):
        http.get_json("https://example.test")

    assert sleeps == [1.0, 2.0]