"""HTTP contract tests; every sample_request uses MockTransport, never live Wikimedia."""

from datetime import UTC, date, datetime

import httpx
import pytest

from wikipedia_interest import wikipedia_client
from wikipedia_interest.models import PageviewError, PageviewRequest
from wikipedia_interest.wikipedia_client import fetch_pageviews

UA = "WikipediaInterestTests/0.1 (https://example.org/contact)"


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(wikipedia_client.time, "sleep", lambda _: None)


@pytest.fixture
def sample_request():
    return PageviewRequest("uk.wikipedia.org", "Астрономія", date(2026, 1, 1), date(2026, 1, 3))


def item(timestamp="2026010100", views=10, **changes):
    return dict(project="uk.wikipedia", article="Астрономія", granularity="daily",
                timestamp=timestamp, access="all-access", agent="user", views=views) | changes


def fetch(sample_request, response):
    with httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client:
        return fetch_pageviews(sample_request, user_agent=UA, client=client)


def fetch_responses(sample_request, responses):
    calls = []

    def handler(request):
        calls.append(request)
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = fetch_pageviews(sample_request, user_agent=UA, client=client)
    assert not responses
    return result, calls


def test_success_sorts_points_preserves_zero_and_sends_defaults(sample_request):
    before = datetime.now(UTC)

    def handler(outgoing):
        assert outgoing.method == "GET"
        assert str(outgoing.url) == (
            "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            "uk.wikipedia.org/all-access/user/"
            "%D0%90%D1%81%D1%82%D1%80%D0%BE%D0%BD%D0%BE%D0%BC%D1%96%D1%8F"
            "/daily/2026010100/2026010300"
        )
        assert outgoing.headers["User-Agent"] == UA
        assert outgoing.headers["Accept"] == "application/json"
        assert outgoing.extensions["timeout"]["read"] == 10.0
        return httpx.Response(200, json={"items": [
            item("2026010300", 3), item("2026010100", 0), item("2026010200", 2),
        ]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        series = fetch_pageviews(sample_request, user_agent=UA, client=client)
        assert not client.is_closed
    assert series.request == sample_request
    assert series.status == "complete"
    assert series.missing_dates == []
    assert [point.views for point in series.points] == [0, 2, 3]
    assert [point.date for point in series.points] == [date(2026, 1, i) for i in (1, 2, 3)]
    assert before <= series.retrieved_at <= datetime.now(UTC)


def test_missing_day_is_not_zero_filled(sample_request):
    series = fetch(sample_request, httpx.Response(200, json={"items": [item(), item("2026010300")]}))
    assert series.status == "partial"
    assert series.missing_dates == [date(2026, 1, 2)]
    assert len(series.points) == 2


@pytest.mark.parametrize("response", [httpx.Response(404), httpx.Response(200, json={"items": []})])
def test_no_data_is_not_article_not_found(sample_request, response):
    series = fetch(sample_request, response)
    assert series.status == "no_data"
    assert series.points == []
    assert series.missing_dates == [date(2026, 1, i) for i in (1, 2, 3)]
    assert any("does not establish whether the article exists" in warning for warning in series.warnings)


@pytest.mark.parametrize("payload", [
    {"items": [item(), item()]},
    *({"items": [item(views=value)]} for value in (-1, True, 2.5, "3", None)),
    *({"items": [item(timestamp=value)]} for value in (
        "2026-01-01", "2026010101", "2026023000", "2026010000", 2026010100,
        "2026010400", "2025123100", "2026010100\n",
    )),
    *({"items": [item(**change)]} for change in (
        {"project": "pl.wikipedia"}, {"article": "Other"}, {"access": "desktop"},
        {"agent": "spider"}, {"granularity": "monthly"},
    )),
    None, [], {}, {"items": None}, {"items": {}}, {"items": [None]},
    {"items": [{"views": 1}]},
])
def test_invalid_responses_are_rejected(sample_request, payload):
    with pytest.raises(PageviewError) as error:
        fetch(sample_request, httpx.Response(200, json=payload))
    assert error.value.code == "INVALID_API_RESPONSE"


def test_invalid_json(sample_request):
    with pytest.raises(PageviewError) as error:
        fetch(sample_request, httpx.Response(200, content=b"<html>unavailable</html>"))
    assert error.value.code == "INVALID_API_RESPONSE"


@pytest.mark.parametrize("status,code", [
    (429, "RATE_LIMITED"), (500, "API_UNAVAILABLE"), (503, "API_UNAVAILABLE"),
    (400, "INVALID_REQUEST"), (403, "ACCESS_BLOCKED"), (302, "UNEXPECTED_HTTP_STATUS"),
])
def test_http_failures(sample_request, status, code):
    with pytest.raises(PageviewError) as error:
        fetch(sample_request, httpx.Response(status, headers={"Retry-After": "60"}))
    assert error.value.code == code
    assert error.value.http_status == status
    assert error.value.retry_after == "60"


@pytest.mark.parametrize("exception", [httpx.ConnectError, httpx.ReadTimeout])
def test_network_failure_exhausts_retry_budget(sample_request, exception):
    calls = []

    def handler(outgoing):
        calls.append(outgoing)
        raise exception("network unavailable", request=outgoing)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PageviewError) as error:
            fetch_pageviews(sample_request, user_agent=UA, client=client)
    assert error.value.code == "API_UNAVAILABLE"
    assert isinstance(error.value.__cause__, exception)
    assert len(calls) == 3


def test_503_then_success(sample_request):
    series, calls = fetch_responses(sample_request, [
        httpx.Response(503),
        httpx.Response(200, json={"items": [item(), item("2026010200"), item("2026010300")]}),
    ])
    assert series.status == "complete"
    assert len(calls) == 2


def test_429_respects_retry_after(sample_request, monkeypatch):
    waits = []
    monkeypatch.setattr(wikipedia_client.time, "sleep", waits.append)
    series, calls = fetch_responses(sample_request, [
        httpx.Response(429, headers={"Retry-After": "2"}),
        httpx.Response(200, json={"items": [item(), item("2026010200"), item("2026010300")]}),
    ])
    assert series.status == "complete"
    assert len(calls) == 2
    assert waits == [2.0]


def test_semantic_http_failure_is_not_retried(sample_request):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(400)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PageviewError) as error:
            fetch_pageviews(sample_request, user_agent=UA, client=client)
    assert error.value.code == "INVALID_REQUEST"
    assert len(calls) == 1


def test_reserved_characters_encoded_once_as_single_segment():
    sample_request = PageviewRequest("uk.wikipedia.org", "Тест /?#%2F", date(2026, 1, 1), date(2026, 1, 1))

    def handler(outgoing):
        assert outgoing.url.raw_path.endswith(
            b"/%D0%A2%D0%B5%D1%81%D1%82_%2F%3F%23%252F/daily/2026010100/2026010100"
        )
        return httpx.Response(200, json={"items": [item(article="Тест_/?#%2F")]})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        assert fetch_pageviews(sample_request, user_agent=UA, client=client).status == "complete"


@pytest.mark.parametrize("article", ["Астрономія", "%D0%90%D1%81%D1%82%D1%80%D0%BE%D0%BD%D0%BE%D0%BC%D1%96%D1%8F"])
def test_response_title_and_project_representations(sample_request, article):
    series = fetch(sample_request, httpx.Response(200, json={"items": [item(article=article, project="uk.wikipedia.org")]}))
    assert len(series.points) == 1


def test_leap_day_and_month_boundary():
    sample_request = PageviewRequest("uk.wikipedia.org", "Астрономія", date(2024, 2, 28), date(2024, 3, 1))
    series = fetch(sample_request, httpx.Response(200, json={"items": [item("2024022800"), item("2024030100")]}))
    assert series.missing_dates == [date(2024, 2, 29)]


@pytest.mark.parametrize("options", [
    {"user_agent": ""}, {"user_agent": "bad\nheader"}, {"timeout": 0},
    {"timeout": float("inf")}, {"timeout": float("nan")}, {"timeout": "10"},
])
def test_invalid_configuration_never_sends_http(sample_request, options):
    def handler(outgoing):
        pytest.fail("Invalid configuration must not send HTTP")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(PageviewError) as error:
            fetch_pageviews(sample_request, client=client, **({"user_agent": UA} | options))
    assert error.value.code == "INVALID_REQUEST"
