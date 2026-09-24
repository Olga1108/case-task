"""Synchronous, daily Wikimedia pageview retrieval without resolution or caching."""

from contextlib import nullcontext
from datetime import UTC, date, datetime, timedelta
import math
import re
import time
from urllib.parse import quote

import httpx

from wikipedia_interest.models import (
    PageviewError, PageviewPoint, PageviewRequest, PageviewSeries,
)

_BASE_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
_MAX_ATTEMPTS = 3
_MAX_RETRY_DELAY = 5.0


def _retry_delay(retry_after: str | None, attempt: int) -> float | None:
    """Return a bounded delay, or None when a server delay is too long."""
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = 2 ** (attempt - 1)
        else:
            if not math.isfinite(delay) or delay < 0:
                delay = 2 ** (attempt - 1)
            elif delay > _MAX_RETRY_DELAY:
                return None
        return min(delay, _MAX_RETRY_DELAY)
    return min(2 ** (attempt - 1), _MAX_RETRY_DELAY)


def _wait_to_retry(retry_after: str | None, attempt: int) -> bool:
    if attempt >= _MAX_ATTEMPTS:
        return False
    delay = _retry_delay(retry_after, attempt)
    if delay is None:
        return False
    time.sleep(delay)
    return True


def fetch_pageviews(
    request: PageviewRequest, *, user_agent: str, timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> PageviewSeries:
    """Fetch one inclusive daily range, raising PageviewError on failure.

    Supply an identifying User-Agent with your application/version and contact.
    A supplied HTTPX client remains owned by the caller; otherwise this function
    opens and closes a client. Timeout applies to each HTTPX network attempt, not
    total elapsed time. Transient failures use at most three attempts and bounded
    waits; final errors preserve RATE_LIMITED/API_UNAVAILABLE and Retry-After.

    HTTP 404 and empty items return no_data, never ARTICLE_NOT_FOUND. This
    function measures only the supplied title, without resolving or merging aliases.
    """
    if not isinstance(request, PageviewRequest):
        raise PageviewError("INVALID_REQUEST", "Expected a PageviewRequest.")
    if (
        not isinstance(user_agent, str) or not user_agent.strip()
        or not user_agent.isascii()
        or any(ord(char) < 32 or ord(char) == 127 for char in user_agent)
    ):
        raise PageviewError("INVALID_REQUEST", "Supply a nonempty ASCII User-Agent without controls.")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise PageviewError("INVALID_REQUEST", "Timeout must be a positive finite number.")

    article = quote(request.article_title.replace(" ", "_"), safe="")
    url = (
        f"{_BASE_URL}/{request.project}/{request.access}/{request.agent}/{article}"
        f"/daily/{request.start_date:%Y%m%d}00/{request.end_date:%Y%m%d}00"
    )
    with nullcontext(client) if client is not None else httpx.Client() as http:
        for attempt in range(1, _MAX_ATTEMPTS + 1):
            try:
                response = http.get(
                    url, headers={"User-Agent": user_agent, "Accept": "application/json"},
                    timeout=timeout, follow_redirects=False,
                )
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                if _wait_to_retry(None, attempt):
                    continue
                raise PageviewError("API_UNAVAILABLE", "Pageview request failed or timed out.") from exc
            except httpx.RequestError as exc:
                raise PageviewError("API_UNAVAILABLE", "Pageview request failed or timed out.") from exc
            if response.status_code == 429 or 500 <= response.status_code < 600:
                retry_after = response.headers.get("Retry-After")
                if _wait_to_retry(retry_after, attempt):
                    continue
            break
        else:
            raise AssertionError("Retry loop exhausted without returning or raising.")

    if response.status_code == 404:
        points = []
    elif response.status_code == 200:
        try:
            payload = response.json()
            points = _parse_points(payload, request)
        except (ValueError, TypeError, KeyError) as exc:
            raise PageviewError("INVALID_API_RESPONSE", f"Invalid pageview response: {exc}") from exc
    else:
        status = response.status_code
        if status == 429:
            code = "RATE_LIMITED"
        elif status >= 500:
            code = "API_UNAVAILABLE"
        elif status in (401, 403):
            code = "ACCESS_BLOCKED"
        elif status == 400:
            code = "INVALID_REQUEST"
        else:
            code = "UNEXPECTED_HTTP_STATUS"
        raise PageviewError(
            code, f"Pageviews API returned HTTP {status}.", http_status=status,
            retry_after=response.headers.get("Retry-After"),
        )

    received = {point.date for point in points}
    missing = [
        day for offset in range((request.end_date - request.start_date).days + 1)
        if (day := request.start_date + timedelta(days=offset)) not in received
    ]
    warnings = ["Only the requested title is measured; aliases and title history are not merged."]
    if not points:
        status = "no_data"
        warnings.append(
            "No pageview data returned: zero traffic and unavailable data cannot be distinguished; "
            "this does not establish whether the article exists."
        )
    elif missing:
        status = "partial"
        warnings.append("Missing days are unknown, not zero views.")
    else:
        status = "complete"
    return PageviewSeries(request, points, missing, status, datetime.now(UTC), warnings)


def _parse_points(payload: object, request: PageviewRequest) -> list[PageviewPoint]:
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError("Expected an object containing an items array.")
    points = []
    seen = set()
    title = request.article_title.replace(" ", "_")
    # Accept Unicode or wire-encoded titles without decoding literal '%' twice.
    titles = (title, request.article_title, quote(title, safe=""))
    for item in payload["items"]:
        if not isinstance(item, dict):
            raise ValueError("Each item must be an object.")
        for key in ("access", "agent", "granularity"):
            if item[key] != getattr(request, key):
                raise ValueError(f"Response {key} does not match request.")
        if item["project"] not in (request.project, request.project.removesuffix(".org")):
            raise ValueError("Response project does not match request.")
        if item["article"] not in titles:
            raise ValueError("Response article does not match request.")
        timestamp = item["timestamp"]
        if not isinstance(timestamp, str) or not re.fullmatch(r"[0-9]{8}00", timestamp):
            raise ValueError("Expected a daily YYYYMMDD00 timestamp.")
        day = date(int(timestamp[:4]), int(timestamp[4:6]), int(timestamp[6:8]))
        if not request.start_date <= day <= request.end_date:
            raise ValueError("Response date is outside the requested range.")
        if day in seen:
            raise ValueError("Duplicate response date.")
        points.append(PageviewPoint(day, item["views"]))
        seen.add(day)
    return sorted(points, key=lambda point: point.date)
