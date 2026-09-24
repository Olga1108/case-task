"""Workflow tests use real retrieval/analysis with mocked HTTP only."""

from copy import deepcopy
from datetime import date

import httpx
import pytest

from wikipedia_interest import research
from wikipedia_interest.models import LanguageMapping, ResolvedTopic, TopicCandidate, WikipediaError

START, END = date(2026, 1, 1), date(2026, 1, 31)
UA = 'ResearchTests/0.1 (https://example.org/contact)'


def mapping(language, valid=True):
    return LanguageMapping(
        language, f'{language}.wikipedia.org', 'valid' if valid else 'LANGUAGE_SITELINK_MISSING',
        article_title=f'Canonical {language}' if valid else None,
        wikidata_id='Q123' if valid else None, warnings=[f'Mapping warning {language}'],
    )


def topic(*mappings):
    return ResolvedTopic('intermittent fasting', 'en', 'Q123', 'partial',
                         TopicCandidate('en', 'Intermittent fasting', wikidata_id='Q123', status='valid'),
                         list(mappings), ['Topic warning'])


def payload(language, missing=(), views=10):
    return {'items': [dict(project=f'{language}.wikipedia', article=f'Canonical_{language}',
                           access='all-access', agent='user', granularity='daily',
                           timestamp=f'202601{day:02d}00', views=views)
                      for day in range(1, 32) if day not in missing]}


def run(resolved, responses):
    calls = []

    def handler(request):
        calls.append(request)
        assert request.url.host == 'wikimedia.org'
        assert '/metrics/pageviews/per-article/' in request.url.path
        assert request.headers['User-Agent'] == UA
        assert request.extensions['timeout']['read'] == 7.0
        assert responses, 'Unexpected HTTP request'
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response if isinstance(response, httpx.Response) else httpx.Response(200, json=response)

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        result = research.research_topic(resolved, START, END, user_agent=UA, timeout=7.0, client=client)
        assert not client.is_closed
    assert not responses
    return result, calls


def test_one_language_full_workflow_defaults_and_warnings():
    result, calls = run(topic(mapping('cs')), [payload('cs')])
    assert result.status == 'completed'
    language, = result.languages
    assert language.status == 'completed'
    assert language.mapping_status == 'valid'
    assert language.analysis.monthly_buckets[0].total_views == 310
    request = language.pageviews.request
    assert (request.project, request.article_title) == ('cs.wikipedia.org', 'Canonical cs')
    assert (request.granularity, request.access, request.agent) == ('daily', 'all-access', 'user')
    assert (request.start_date, request.end_date) == (START, END)
    assert calls[0].url.path.endswith('/cs.wikipedia.org/all-access/user/Canonical_cs/daily/2026010100/2026013100')
    assert 'Mapping warning cs' in language.warnings
    assert set(language.pageviews.warnings) <= set(language.warnings)
    assert set(language.analysis.warnings) <= set(language.warnings)
    assert result.warnings == ['Topic warning']


def test_two_languages_keep_order_and_inputs_unchanged():
    resolved = topic(mapping('uk'), mapping('cs'))
    original = deepcopy(resolved)
    result, calls = run(resolved, [payload('uk'), payload('cs')])
    assert result.status == 'completed'
    assert [r.language for r in result.languages] == ['uk', 'cs']
    assert all(r.analysis is not None for r in result.languages)
    assert len(calls) == 2
    assert resolved == original
    result.languages[0].warnings.append('Result-only warning')
    result.warnings.append('Result-only warning')
    assert resolved == original


def test_intermittent_fasting_czech_valid_polish_missing():
    resolved = topic(mapping('cs'), mapping('pl', False))
    error = WikipediaError('LANGUAGE_SITELINK_MISSING', 'No Polish sitelink')
    resolved.language_mappings[1].error = error
    result, calls = run(resolved, [payload('cs')])
    assert result.status == 'partial'
    czech, polish = result.languages
    assert czech.analysis is not None
    assert polish.status == 'mapping_unavailable'
    assert polish.mapping_status == 'LANGUAGE_SITELINK_MISSING'
    assert polish.error is error
    assert polish.analysis is polish.pageviews is None
    assert polish.warnings == ['Mapping warning pl']
    assert len(calls) == 1 and '/cs.wikipedia.org/' in calls[0].url.path


@pytest.mark.parametrize('response', [httpx.Response(503), httpx.ConnectError('offline')])
def test_individual_failure_does_not_abort_later_languages(response):
    result, calls = run(topic(mapping('uk'), mapping('cs'), mapping('pl', False)), [response, payload('cs')])
    assert result.status == 'partial'
    assert [r.status for r in result.languages] == ['retrieval_failed', 'completed', 'mapping_unavailable']
    assert result.languages[0].error.code == 'API_UNAVAILABLE'
    assert result.languages[1].analysis is not None
    assert len(calls) == 2


def test_all_mappings_unavailable():
    resolved = topic(mapping('pl', False), mapping('cs', False))
    resolved.status = 'unresolved'
    result, calls = run(resolved, [])
    assert result.status == 'failed'
    assert calls == []
    assert all(r.error.code == 'LANGUAGE_SITELINK_MISSING' for r in result.languages)


def test_all_retrievals_fail_preserves_retry_details():
    result, calls = run(topic(mapping('cs'), mapping('uk')),
                        [httpx.Response(503), httpx.Response(429, headers={'Retry-After': '60'})])
    assert result.status == 'failed'
    assert len(calls) == 2
    assert result.languages[1].error.code == 'RATE_LIMITED'
    assert result.languages[1].error.retry_after == '60'
    assert all(r.status == 'retrieval_failed' for r in result.languages)


@pytest.mark.parametrize('response', [httpx.Response(404), httpx.Response(200, json={'items': []})])
def test_no_data_is_completed_workflow_not_zero_or_article_missing(response):
    result, _ = run(topic(mapping('cs')), [response])
    language, = result.languages
    assert result.status == 'completed'
    assert language.status == language.pageviews.status == 'no_data'
    assert language.error is None
    assert language.analysis is not None
    assert language.pageviews.points == []
    assert len(language.pageviews.missing_dates) == 31
    assert language.analysis.monthly_buckets[0].total_views is None


def test_partial_series_retained_and_analyzed():
    result, _ = run(topic(mapping('cs')), [payload('cs', missing=(15,))])
    language, = result.languages
    assert result.status == 'completed'
    assert language.status == 'partial_data'
    assert language.pageviews.status == 'partial'
    assert language.pageviews.missing_dates == [date(2026, 1, 15)]
    assert len(language.pageviews.points) == 30
    assert language.analysis.monthly_buckets[0].total_views == 300
    assert not language.analysis.monthly_buckets[0].complete
    assert set(language.pageviews.warnings + language.analysis.warnings) <= set(language.warnings)


def test_explicit_zero_days_are_completed_data():
    result, _ = run(topic(mapping('cs')), [payload('cs', views=0)])
    language, = result.languages
    assert language.status == 'completed'
    assert len(language.pageviews.points) == 31
    assert language.analysis.monthly_buckets[0].complete
    assert language.analysis.monthly_buckets[0].total_views == 0


@pytest.mark.parametrize('failure', [False, True])
def test_internal_client_is_created_once_and_closed(monkeypatch, failure):
    calls = []

    def handler(request):
        calls.append(request)
        language = 'cs' if len(calls) == 1 else 'uk'
        return httpx.Response(503) if failure else httpx.Response(200, json=payload(language))

    owned = httpx.Client(transport=httpx.MockTransport(handler))
    created = []

    def factory():
        created.append(owned)
        return owned

    monkeypatch.setattr(research.httpx, 'Client', factory)
    result = research.research_topic(topic(mapping('cs'), mapping('uk')), START, END, user_agent=UA)
    assert result.status == ('failed' if failure else 'completed')
    assert created == [owned]
    assert owned.is_closed
    assert len(calls) == 2


@pytest.mark.parametrize('changes', [
    {'start_date': '2026-01-01'}, {'end_date': date(2025, 1, 1)},
    {'start_date': date(2015, 1, 1)}, {'user_agent': ''},
    {'timeout': float('nan')}, {'resolved_topic': None},
])
def test_invalid_shared_input_raises_before_http(changes):
    def handler(request):
        pytest.fail('No HTTP expected')
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        arguments = dict(resolved_topic=topic(mapping('cs')), start_date=START, end_date=END,
                         user_agent=UA, client=client) | changes
        with pytest.raises(WikipediaError) as error:
            research.research_topic(**arguments)
    assert error.value.code == 'INVALID_REQUEST'


def test_unselected_topic_rejected():
    resolved = topic(mapping('cs'))
    resolved.selected_candidate.status = 'unvalidated'
    with pytest.raises(WikipediaError, match='validated selection'):
        research.research_topic(resolved, START, END, user_agent=UA)


def test_mismatched_mapping_identity_does_not_fetch():
    wrong = mapping('uk')
    wrong.wikidata_id = 'Q999'
    result, calls = run(topic(wrong, mapping('cs')), [payload('cs')])
    assert result.status == 'partial'
    assert result.languages[0].status == 'mapping_unavailable'
    assert result.languages[0].error.code == 'TOPIC_MAPPING_MISMATCH'
    assert len(calls) == 1


def test_analysis_domain_error_retains_series_and_continues(monkeypatch):
    real_analyze = research.analyze_pageviews

    def analyze(series):
        if series.request.project == 'uk.wikipedia.org':
            raise WikipediaError('INVALID_REQUEST', 'Invalid analysis input')
        return real_analyze(series)

    monkeypatch.setattr(research, 'analyze_pageviews', analyze)
    result, _ = run(topic(mapping('uk'), mapping('cs')), [payload('uk'), payload('cs')])
    assert result.status == 'partial'
    assert result.languages[0].status == 'analysis_failed'
    assert result.languages[0].pageviews is not None
    assert result.languages[0].analysis is None
    assert result.languages[1].analysis is not None
