"""Synthetic evidence presentation contracts; no network."""

from copy import deepcopy
from dataclasses import asdict
from datetime import date, timedelta
import json

import pytest

from tests.test_analysis import series
from tests.test_research import mapping, topic
from wikipedia_interest.analysis import analyze_pageviews
from wikipedia_interest.models import LanguageResearchResult, ResearchResult, WikipediaError
from wikipedia_interest.presentation import build_agent_summary


def example(languages=('cs', 'uk'), missing=(), empty=False):
    start, end = date(2024, 1, 1), date(2025, 12, 31)
    resolved = topic(*(mapping(lang) for lang in languages))
    resolved.selected_candidate.article_title = 'Intermittent fasting'
    results = []
    for lang in languages:
        sample = series(start, end, lambda day: 100 + day.day % 7 + (day.year - 2024) * 10,
                        missing=missing)
        if empty:
            sample.points = []
            sample.missing_dates = [start + timedelta(days=i) for i in range((end - start).days + 1)]
            sample.status = 'no_data'
        analysis = analyze_pageviews(sample)
        results.append(LanguageResearchResult(lang, f'{lang}.wikipedia.org', f'Canonical {lang}',
                                             'valid', 'no_data' if empty else 'partial_data' if missing else 'completed',
                                             sample, analysis, warnings=analysis.warnings[:]))
    return ResearchResult(resolved, start, end, results, 'completed', ['Shared warning', 'Shared warning'])


def test_metadata_order_serialization_size_and_no_mutation():
    result = example()
    original = deepcopy(result)
    summary = build_agent_summary(result)
    assert summary['topic'] == dict(query='intermittent fasting', wikidata_id='Q123',
                                   selected_article='Intermittent fasting', query_language='en')
    assert summary['period'] == {'start': '2024-01-01', 'end': '2025-12-31'}
    assert summary['workflow_status'] == 'completed'
    assert [r['language'] for r in summary['languages']] == ['cs', 'uk']
    encoded = json.dumps(summary, allow_nan=False)
    naive = repr(asdict(result))

    assert len(encoded) < len(naive)
    assert result == original
    assert summary == build_agent_summary(result)


def test_success_growth_trend_and_seasonality_use_existing_evidence():
    result = example(('cs',))
    analysis = result.languages[0].analysis
    item = build_agent_summary(result)['languages'][0]
    assert item['data']['observation_count'] == 731
    assert item['data']['complete_months'] == 24
    assert item['data']['incomplete_months'] == 0
    assert item['data']['observed_start'] == '2024-01-01'
    assert item['data']['observed_end'] == '2025-12-31'
    assert item['growth']['latest_3m_yoy']['value'] == analysis.growth.latest_3m_yoy.value
    assert item['growth']['latest_3m_yoy']['old_months'] == ['2024-10-01', '2024-11-01', '2024-12-01']
    assert item['growth']['latest_3m_yoy']['new_months'] == ['2025-10-01', '2025-11-01', '2025-12-01']
    comparisons = item['growth']['same_month_yoy']
    assert len(comparisons) == 6
    assert comparisons[0]['new_months'] == ['2025-07-01']
    assert item['trend']['theil_sen_slope'] == analysis.trend.theil_sen_slope
    assert item['trend']['normalized_theil_sen_slope'] == analysis.trend.normalized_theil_sen_slope
    assert item['trend']['normalization'] == 'mean monthly total_views'
    assert item['seasonality']['enough_history_for_annual_comparison']
    descriptors = item['seasonality']['month_of_year']
    assert [d['month'] for d in descriptors] == list(range(1, 13))
    for record in descriptors:
        source = analysis.seasonality.month_of_year[record['month']]
        assert record['average_daily_views'] == source.average_daily_views
        assert record['contributing_months'] == 2
        assert record['years'] == [2024, 2025]


def test_partial_and_unavailable_growth():
    item = build_agent_summary(example(missing=[date(2025, 12, 15)]))['languages'][0]
    assert item['workflow_status'] == 'partial_data'
    assert item['data']['status'] == 'partial'
    assert item['data']['missing_day_count'] == 1
    assert item['data']['observation_count'] == 730
    assert item['data']['complete_months'] == 23
    assert item['data']['incomplete_months'] == 1
    assert item['growth']['latest_3m_yoy']['value'] is None
    assert item['growth']['latest_3m_yoy']['reason'] == 'MISSING_OR_INCOMPLETE_MONTHS'


def test_no_data_preserved_without_zero_traffic():
    item = build_agent_summary(example(empty=True))['languages'][0]
    assert item['data']['status'] == item['workflow_status'] == 'no_data'
    assert item['data']['observation_count'] == item['data']['zero_day_count'] == 0
    assert item['data']['observed_start'] is item['data']['observed_end'] is None
    assert item['data']['complete_months'] == 0
    assert item['trend']['theil_sen_slope'] is None
    assert all(d['average_daily_views'] is None for d in item['seasonality']['month_of_year'])


@pytest.mark.parametrize('status,code,http_status', [
    ('mapping_unavailable', 'LANGUAGE_SITELINK_MISSING', None),
    ('retrieval_failed', 'API_UNAVAILABLE', 503),
])
def test_failures_remain_explicit(status, code, http_status):
    result = example(('cs',))
    result.languages[0] = LanguageResearchResult('pl', 'pl.wikipedia.org', None,
        code if status == 'mapping_unavailable' else 'valid', status,
        error=WikipediaError(code, 'Unavailable', http_status=http_status,
                             retry_after='60' if http_status else None))
    item = build_agent_summary(result)['languages'][0]
    assert item['workflow_status'] == status
    assert all(item[key] is None for key in ('data', 'growth', 'trend', 'anomalies', 'sensitivity', 'seasonality'))
    assert item['error']['code'] == code
    assert item['error']['message'] == 'Unavailable'
    if http_status:
        assert item['error']['http_status'] == 503
        assert item['error']['retry_after'] == '60'
    else:
        assert set(item['error']) == {'code', 'message'}


def test_bounded_anomalies_and_sensitivity():
    result = example(('cs',))
    sample = series(result.start_date, result.end_date,
                    lambda day: 10000 + day.day if day.day == 15 else 100 + day.day % 7)
    result.languages[0].pageviews = sample
    analysis = result.languages[0].analysis = analyze_pageviews(sample)
    item = build_agent_summary(result)['languages'][0]
    for method, source in analysis.anomalies.items():
        assert item['anomalies'][method]['flagged_count'] == len(source.flagged_points)
        assert item['anomalies'][method]['status'] == source.status
    examples = item['anomalies']['mad']['largest_examples']
    assert len(examples) == 5
    assert examples[0] == {'date': '2024-01-15', 'views': 10015}
    assert item['anomalies']['mad']['flagged_count'] == 24
    sensitivity = item['sensitivity']
    assert sensitivity['excluded_observation_count'] == 24
    assert sensitivity['input_measure'] == 'average_daily_views'
    assert sensitivity['slope_units'] == 'views/day per calendar month'
    for side in ('before', 'after'):
        assert sensitivity[side]['normalized_theil_sen_slope'] == getattr(analysis.sensitivity, side).normalized_theil_sen_slope
        assert sensitivity[side]['normalized_ols_slope'] == getattr(analysis.sensitivity, side).normalized_ols_slope


def test_warning_catalog_deduplicates_across_scopes_and_retains_references():
    result = example()
    result.languages[0].pageviews.warnings += ['Shared warning', 'Series warning']
    summary = build_agent_summary(result)
    warnings = summary['warnings']
    assert len(warnings) == len(set(warnings))
    assert 'Series warning' in warnings
    assert 'Shared warning' in [warnings[i] for i in summary['warning_ids']]
    for item in summary['languages']:
        assert all(warnings[i] in result.languages[0].analysis.warnings for i in item['warning_ids'])
    refs = summary['languages'][0]['data']['warning_ids']
    assert [warnings[i] for i in refs] == ['Shared warning', 'Series warning']


def test_no_full_observation_exports_or_interpretation_fields():
    forbidden = {'points', 'flagged_points', 'monthly_buckets', 'adjusted_months', 'excluded_dates',
                 'recommendation', 'winner', 'best_market', 'launch', 'market_score', 'confidence_score',
                 'trend_label', 'increasing', 'decreasing', 'stable', 'is_seasonal'}

    def visit(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            assert len(value) < 100  # fixture has 731 daily points per language
            for child in value:
                visit(child)
        else:
            assert value is None or type(value) in (str, int, float, bool)
    visit(build_agent_summary(example()))


def test_explicit_zero_observations():
    result = example(('cs',))
    result.languages[0].pageviews = series(result.start_date, result.end_date, lambda day: 0)
    result.languages[0].analysis = analyze_pageviews(result.languages[0].pageviews)
    item = build_agent_summary(result)['languages'][0]
    assert item['data']['zero_day_count'] == 731
    assert item['trend']['theil_sen_slope'] == 0
    assert item['anomalies']['mad']['reason'] == 'ZERO_DISPERSION'
