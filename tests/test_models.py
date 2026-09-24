"""Validation of the public retrieval records."""

from datetime import date, datetime

import pytest

from wikipedia_interest.models import PageviewError, PageviewPoint, PageviewRequest


def test_request_defaults_and_unencoded_title():
    request = PageviewRequest("uk.wikipedia.org", "Астрономія / 100%", date(2026, 1, 1), date(2026, 1, 1))
    assert (request.granularity, request.access, request.agent) == ("daily", "all-access", "user")
    assert request.article_title == "Астрономія / 100%"


@pytest.mark.parametrize("changes", [
    {"project": "https://uk.wikipedia.org"}, {"project": "uk.wikipedia.org/extra"},
    {"project": None}, {"article_title": " "}, {"article_title": "bad\nheader"},
    {"start_date": "2026-01-01"}, {"start_date": datetime(2026, 1, 1)},
    {"start_date": date(2026, 1, 3)}, {"start_date": date(2015, 6, 30)},
    {"granularity": "monthly"}, {"access": "all"}, {"agent": "human"},
])
def test_invalid_request(changes):
    values = dict(project="en.wikipedia.org", article_title="Example",
                  start_date=date(2026, 1, 1), end_date=date(2026, 1, 2))
    with pytest.raises(PageviewError) as error:
        PageviewRequest(**(values | changes))
    assert error.value.code == "INVALID_REQUEST"


@pytest.mark.parametrize("views", [-1, True, 1.5, "2", None])
def test_point_rejects_invalid_counts(views):
    with pytest.raises(PageviewError):
        PageviewPoint(date(2026, 1, 1), views)


def test_point_preserves_zero_and_rejects_string_date():
    assert PageviewPoint(date(2026, 1, 1), 0).views == 0
    with pytest.raises(PageviewError):
        PageviewPoint("2026-01-01", 1)


def test_generic_error_keeps_pageview_compatibility():
    from wikipedia_interest.models import WikipediaError

    assert PageviewError is WikipediaError
    error = WikipediaError("RATE_LIMITED", "Slow down", http_status=429, retry_after="30")
    assert str(error) == "Slow down"
    assert error.code == "RATE_LIMITED"
    assert error.http_status == 429
    assert error.retry_after == "30"


def test_topic_records_have_independent_warning_lists():
    from wikipedia_interest.models import LanguageMapping, TopicCandidate

    first = TopicCandidate("en", "First")
    second = TopicCandidate("en", "Second")
    first.warnings.append("Missing identity")
    assert second.warnings == []
    mapping = LanguageMapping("pl", "pl.wikipedia.org", "LANGUAGE_SITELINK_MISSING")
    assert mapping.wikidata_id is None
    assert mapping.article_title is None
