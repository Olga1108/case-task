"""Machine CLI contracts with mocked domain calls; live HTTP is prohibited."""

from datetime import date
import json
from pathlib import Path

import pytest

from tests.test_presentation import example
from wikipedia_interest import cli, charts
from wikipedia_interest.models import LanguageResearchResult, TopicCandidate, WikipediaError

UA = 'Tests/1 (https://example.org/contact)'
BASE = ['research', '--query', 'intermittent fasting', '--query-language', 'en',
        '--selected-title', 'Intermittent fasting', '--languages', 'uk,cs']


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        pytest.fail('Live HTTP is forbidden')
    monkeypatch.setattr(cli.httpx.Client, 'send', fail)
    monkeypatch.setenv('WIKIPEDIA_USER_AGENT', UA)
    monkeypatch.setattr(cli, '_today', lambda: date(2026, 9, 24))


@pytest.fixture
def workflow(monkeypatch):
    result = example(('uk', 'cs'))
    calls = []

    def map_languages(query, selected, languages, **kwargs):
        calls.append(('map', query, selected, languages, kwargs))
        assert selected.source_language == 'en'
        assert selected.input_title == 'Intermittent fasting'
        return result.topic

    def research(resolved, start, end, **kwargs):
        calls.append(('research', resolved, start, end, kwargs))
        assert resolved is result.topic
        result.start_date, result.end_date = start, end
        return result

    monkeypatch.setattr(cli, 'map_topic_languages', map_languages)
    monkeypatch.setattr(cli, 'research_topic', research)
    return result, calls


def invoke(capsys, args):
    code = cli.main(args)
    output = capsys.readouterr()
    assert output.err == ''
    return code, json.loads(output.out)


def test_search_json_evidence_without_selection(monkeypatch, capsys):
    candidates = [TopicCandidate('en', 'First', article_title='First', canonical_url='https://en.wikipedia.org/wiki/First',
                                wikidata_id='Q1', search_rank=1, snippet='Clean snippet', status='valid'),
                  TopicCandidate('en', 'Second', search_rank=2, is_disambiguation=True,
                                 status='DISAMBIGUATION_PAGE', error=WikipediaError('DISAMBIGUATION_PAGE', 'Ambiguous'))]
    calls = []
    def search(*args, **kwargs):
        calls.append((args, kwargs))
        return candidates
    monkeypatch.setattr(cli, 'search_topic_candidates', search)
    code, payload = invoke(capsys, ['search', '--query', 'topic', '--query-language', 'en'])
    assert code == 0
    assert len(payload['candidates']) == 2
    assert 'selected' not in payload
    first, second = payload['candidates']
    assert first['snippet'] == 'Clean snippet'
    assert first['wikidata_id'] == 'Q1'
    assert first['search_rank'] == 1
    assert first['canonical_url'].endswith('/First')
    assert second['is_disambiguation']
    assert second['error']['code'] == 'DISAMBIGUATION_PAGE'
    assert calls == [(('topic', 'en'), {'user_agent': UA})]


def test_research_selection_identity_order_defaults_and_no_raw_arrays(workflow, capsys):
    result, calls = workflow
    code, payload = invoke(capsys, BASE + ['--expected-qid', 'Q123'])
    assert code == 0
    assert [item['language'] for item in payload['languages']] == ['uk', 'cs']
    assert payload['period'] == {'start': '2024-09-01', 'end': '2026-08-31'}
    assert payload['execution']['period_mode'] == 'last_24_complete_months'
    assert calls[0][2].wikidata_id == 'Q123'
    assert calls[0][3] == ['uk', 'cs']
    assert calls[0][-1]['client'] is calls[1][-1]['client']
    assert calls[0][-1]['client'].is_closed
    assert '"points"' not in json.dumps(payload, allow_nan=False)


@pytest.mark.parametrize('today,start,end', [
    (date(2026, 1, 1), date(2024, 1, 1), date(2025, 12, 31)),
    (date(2024, 3, 31), date(2022, 3, 1), date(2024, 2, 29)),
])
def test_default_calendar_boundaries(monkeypatch, today, start, end):
    monkeypatch.setattr(cli, '_today', lambda: today)
    assert cli._period(None, None, None)[:2] == (start, end)


@pytest.mark.parametrize('extra,start,end,mode', [
    (['--start', '2024-02-01', '--end', '2024-02-29'], '2024-02-01', '2024-02-29', 'explicit'),
    (['--months', '12'], '2025-09-01', '2026-08-31', 'last_12_complete_months'),
])
def test_explicit_and_relative_period(workflow, capsys, extra, start, end, mode):
    code, payload = invoke(capsys, BASE + extra)
    assert code == 0
    assert payload['period'] == {'start': start, 'end': end}
    assert payload['execution']['period_mode'] == mode


@pytest.mark.parametrize('state', ['mapping_unavailable', 'no_data', 'partial_data'])
def test_partial_states_are_successful_commands(workflow, capsys, state):
    result, _ = workflow
    if state == 'mapping_unavailable':
        result.status = 'partial'
        result.languages[1] = LanguageResearchResult('cs', 'cs.wikipedia.org', None,
            'LANGUAGE_SITELINK_MISSING', state, error=WikipediaError('LANGUAGE_SITELINK_MISSING', 'Absent'))
    else:
        fixture = example(('cs',), empty=state == 'no_data', missing=[date(2025, 12, 1)] if state == 'partial_data' else ())
        result.languages[1] = fixture.languages[0]
    code, payload = invoke(capsys, BASE)
    assert code == 0
    assert payload['languages'][1]['workflow_status'] == state
    if state == 'mapping_unavailable':
        assert payload['workflow_status'] == 'partial'
        assert payload['languages'][1]['error']['code'] == 'LANGUAGE_SITELINK_MISSING'
    else:
        assert payload['languages'][1]['data']['status'] == ('partial' if state == 'partial_data' else 'no_data')


def test_chart_path(workflow, monkeypatch, capsys, tmp_path):
    target = tmp_path / 'chosen.png'
    calls = []
    def render(result, path):
        calls.append((result, path))
        path.write_bytes(b'test chart')
        return path
    monkeypatch.setattr(charts, 'render_monthly_chart', render)
    code, payload = invoke(capsys, BASE + ['--chart', str(target)])
    assert code == 0
    assert calls == [(workflow[0], target)]
    assert payload['execution']['chart_path'] == str(target)
    assert target.exists()


@pytest.mark.parametrize('error', [ValueError('No complete source monthly data'), OSError('Cannot write chart')])
def test_chart_failure_preserves_research(workflow, monkeypatch, capsys, error):
    def render(*args):
        raise error
    monkeypatch.setattr(charts, 'render_monthly_chart', render)
    code, payload = invoke(capsys, BASE + ['--chart', 'chart.png'])
    assert code == 0
    assert payload['languages'][0]['trend'] is not None
    assert payload['execution']['chart_path'] is None
    assert payload['execution']['chart_error'] == {'code': 'CHART_UNAVAILABLE', 'message': str(error)}


@pytest.mark.parametrize('extra', [
    ['--languages', 'cs,cs'], ['--languages', 'cs,'], ['--languages', '../pl'],
    ['--query-language', 'EN'], ['--start', '2024-01-01'], ['--months', '0'],
    ['--start', 'bad', '--end', '2025-01-01'],
    ['--start', '20250101', '--end', '2025-01-31'],
    ['--start', '2025-02-01', '--end', '2025-01-01'],
    ['--start', '2014-01-01', '--end', '2015-01-01'],
    ['--start', '2024-01-01', '--end', '2025-01-01', '--months', '12'],
    ['--expected-qid', 'not-qid'], ['--months', 'oops'], ['--unknown'],
])
def test_invalid_inputs_fail_before_domain_calls(workflow, capsys, extra):
    code, payload = invoke(capsys, BASE + extra)
    assert code == 2
    assert payload['error']['code'] == 'INVALID_REQUEST'
    assert workflow[1] == []


def test_missing_user_agent(monkeypatch, capsys):
    monkeypatch.delenv('WIKIPEDIA_USER_AGENT')
    code, payload = invoke(capsys, BASE)
    assert code == 2
    assert 'user-agent' in payload['error']['message']


def test_shared_domain_error(monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise WikipediaError('RATE_LIMITED', 'Try later', http_status=429, retry_after='60')
    monkeypatch.setattr(cli, 'map_topic_languages', fail)
    code, payload = invoke(capsys, BASE)
    assert code == 2
    assert payload['error'] == {'code': 'RATE_LIMITED', 'message': 'Try later', 'http_status': 429, 'retry_after': '60'}


def test_missing_arguments_json(capsys):
    code, payload = invoke(capsys, ['research'])
    assert code == 2
    assert payload['error']['code'] == 'INVALID_REQUEST'
