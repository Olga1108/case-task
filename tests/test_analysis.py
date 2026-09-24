"""Synthetic numeric contracts for deterministic analysis; no network or datasets."""

from calendar import monthrange
from copy import deepcopy
from datetime import UTC, date, datetime, timedelta

import pytest

from wikipedia_interest.analysis import (
    aggregate_monthly, analyze_pageviews, calculate_growth, calculate_trend,
    describe_seasonality, detect_anomalies,
)
from wikipedia_interest.models import PageviewPoint, PageviewRequest, PageviewSeries, WikipediaError


def series(start, end, value=lambda day: 10, missing=()):
    days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    points = [PageviewPoint(day, value(day)) for day in days if day not in missing]
    return PageviewSeries(PageviewRequest('en.wikipedia.org', 'Synthetic', start, end),
                          points, list(missing), 'partial' if missing else 'complete',
                          datetime(2026, 1, 1, tzinfo=UTC))


def totals(values, start=date(2024, 1, 1)):
    """Distribute exact integer monthly totals across every day without gaps."""
    origin = start.year * 12 + start.month - 1
    final_year, final_month = divmod(origin + len(values) - 1, 12)
    end = date(final_year, final_month + 1, monthrange(final_year, final_month + 1)[1])

    def daily(day):
        total = values[day.year * 12 + day.month - 1 - origin]
        base, remainder = divmod(total, monthrange(day.year, day.month)[1])
        return base + (day.day <= remainder)
    return series(start, end, daily)


def growth(sample):
    return calculate_growth(aggregate_monthly(sample), sample.request.start_date, sample.request.end_date)


@pytest.mark.parametrize('year,month,days', [(2025, 1, 31), (2025, 2, 28), (2024, 2, 29)])
def test_complete_calendar_month(year, month, days):
    bucket, = aggregate_monthly(series(date(year, month, 1), date(year, month, days)))
    assert bucket.complete
    assert bucket.observed_days == bucket.expected_days == days
    assert bucket.total_views == days * 10
    assert bucket.average_daily_views == bucket.median_daily_views == 10


def test_observed_zero_sum_mean_median():
    bucket, = aggregate_monthly(series(date(2025, 1, 1), date(2025, 1, 31), lambda day: day.day - 1))
    assert bucket.observed_days == 31
    assert bucket.complete
    assert bucket.total_views == 465
    assert bucket.average_daily_views == bucket.median_daily_views == 15


def test_partial_boundary_months_remain_visible_but_excluded():
    sample = series(date(2025, 1, 15), date(2025, 3, 12))
    buckets = aggregate_monthly(sample)
    assert [b.complete for b in buckets] == [False, True, False]
    assert [b.observed_days for b in buckets] == [17, 28, 12]
    assert calculate_trend(buckets).ols_slope is None
    assert growth(sample).first_vs_last.value is None


def test_internal_missing_day_excludes_month_without_imputation():
    sample = series(date(2025, 1, 1), date(2025, 3, 31), missing=[date(2025, 2, 7)])
    buckets = aggregate_monthly(sample)
    assert [b.complete for b in buckets] == [True, False, True]
    assert buckets[1].observed_days == 27
    assert buckets[1].total_views == 270
    assert buckets[1].average_daily_views == 10


def test_whole_missing_month_is_not_zero():
    sample = series(date(2025, 1, 1), date(2025, 3, 31),
                    missing=[date(2025, 2, day) for day in range(1, 29)])
    bucket = aggregate_monthly(sample)[1]
    assert bucket.observed_days == 0
    assert bucket.total_views is bucket.average_daily_views is bucket.median_daily_views is None
    assert not bucket.complete


def test_completeness_uses_points_not_status_or_missing_metadata():
    sample = totals([100])
    sample.status = 'partial'
    sample.missing_dates = [date(2024, 1, 1)]
    assert aggregate_monthly(sample)[0].complete


@pytest.mark.parametrize('duplicate', [True, False])
def test_invalid_points_are_rejected(duplicate):
    sample = totals([100])
    sample.points.append(sample.points[0] if duplicate else PageviewPoint(date(2023, 1, 1), 1))
    with pytest.raises(WikipediaError):
        aggregate_monthly(sample)


def test_first_last_and_window_growth():
    result = growth(totals([100 * i for i in range(1, 13)]))
    assert result.first_vs_last.value == 11
    assert result.first_3m_vs_last_3m.value == pytest.approx((1100 - 200) / 200)
    assert result.first_6m_vs_last_6m.value == pytest.approx((950 - 350) / 350)
    assert len(result.first_6m_vs_last_6m.old_months) == 6


@pytest.mark.parametrize('count,field', [(1, 'first_vs_last'), (5, 'first_3m_vs_last_3m'), (11, 'first_6m_vs_last_6m')])
def test_edge_windows_require_distinct_nonoverlapping_months(count, field):
    metric = getattr(growth(totals([100] * count)), field)
    assert metric.value is None
    assert metric.reason == 'INSUFFICIENT_NONOVERLAPPING_MONTHS'


def test_same_month_yoy_and_latest_three_alignment():
    # Jan 2025 through Aug 2026; June-August 2025 differs from Jan-March.
    sample = totals([100, 100, 100, 100, 100, 200, 300, 400, 100, 100, 100, 100,
                     150, 150, 150, 150, 150, 400, 600, 800], date(2025, 1, 1))
    result = growth(sample)
    assert result.same_month_yoy[date(2026, 6, 1)].value == 1
    latest = result.latest_3m_yoy
    assert latest.old_months == [date(2025, month, 1) for month in (6, 7, 8)]
    assert latest.new_months == [date(2026, month, 1) for month in (6, 7, 8)]
    assert latest.value == 1
    assert result.same_month_yoy[date(2025, 1, 1)].value is None


@pytest.mark.parametrize('missing', [date(2025, 7, 1), date(2026, 7, 1), date(2026, 8, 1)])
def test_yoy_missing_month_does_not_shift_window(missing):
    sample = series(date(2025, 1, 1), date(2026, 8, 31), missing=[missing])
    metric = growth(sample).latest_3m_yoy
    assert metric.value is None
    assert metric.reason == 'MISSING_OR_INCOMPLETE_MONTHS'
    assert metric.new_months[-1] == date(2026, 8, 1)


def test_yoy_crosses_year_and_ignores_partial_end_month():
    sample = series(date(2024, 1, 1), date(2026, 2, 10))
    metric = growth(sample).latest_3m_yoy
    assert metric.new_months == [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)]
    assert metric.old_months == [date(2024, 11, 1), date(2024, 12, 1), date(2025, 1, 1)]
    assert metric.value == 0


def test_growth_zero_denominator():
    result = growth(totals([0] * 12 + [100] * 12))
    for metric in (result.first_vs_last, result.first_3m_vs_last_3m,
                   result.first_6m_vs_last_6m, result.latest_3m_yoy,
                   result.same_month_yoy[date(2025, 1, 1)]):
        assert metric.value is None
        assert metric.reason == 'ZERO_DENOMINATOR'


@pytest.mark.parametrize('values,slope', [([100, 200, 300], 100), ([300, 200, 100], -100), ([100, 100, 100], 0)])
def test_exact_trend_and_normalization(values, slope):
    trend = calculate_trend(aggregate_monthly(totals(values)))
    assert trend.ols_slope == pytest.approx(slope)
    assert trend.theil_sen_slope == pytest.approx(slope)
    assert trend.normalized_ols_slope == pytest.approx(slope / (sum(values) / len(values)))
    assert trend.normalized_theil_sen_slope == trend.normalized_ols_slope


def test_calendar_gap_does_not_compress_slope():
    sample = totals([100, 200, 300])
    sample.points = [p for p in sample.points if p.date.month != 2]
    trend = calculate_trend(aggregate_monthly(sample))
    assert trend.ols_slope == trend.theil_sen_slope == 100


def test_theil_sen_resists_outlier():
    trend = calculate_trend(aggregate_monthly(totals([100, 200, 300, 400, 500, 600, 700, 100000])))
    assert trend.theil_sen_slope == 100
    assert trend.ols_slope > 1000


def test_zero_and_insufficient_trends():
    zero = calculate_trend(aggregate_monthly(totals([0, 0])))
    assert zero.ols_slope == zero.theil_sen_slope == 0
    assert zero.normalized_ols_slope is zero.normalized_theil_sen_slope is None
    assert zero.warnings
    for buckets in ([], aggregate_monthly(totals([10]))):
        trend = calculate_trend(buckets)
        assert trend.ols_slope is trend.theil_sen_slope is None
        assert trend.warnings


def test_each_diagnostic_detects_spike_and_scores():
    points = [PageviewPoint(date(2025, 1, 1) + timedelta(days=i), value)
              for i, value in enumerate([98, 99, 100, 101, 102] * 20 + [10000])]
    before = deepcopy(points)
    results = detect_anomalies(points)
    for method, result in results.items():
        assert result.status == 'available'
        assert [p.date for p in result.flagged_points] == [points[-1].date]
        assert result.flagged_points[0].views == 10000
        if method == 'iqr':
            assert result.flagged_points[0].score is None
        else:
            assert result.flagged_points[0].score > 3.5
    assert points == before


def test_diagnostics_detect_low_outlier_and_preserve_zero():
    points = [PageviewPoint(date(2025, 1, 1) + timedelta(days=i), value)
              for i, value in enumerate([98, 99, 100, 101, 102] * 20 + [0])]
    for result in detect_anomalies(points).values():
        assert result.flagged_points[0].views == 0


def test_zero_dispersion_is_unavailable_not_evidence_of_no_anomalies():
    points = [PageviewPoint(date(2025, 1, day), 10000 if day == 31 else 100) for day in range(1, 32)]
    results = detect_anomalies(points)
    assert results['mad'].reason == results['iqr'].reason == 'ZERO_DISPERSION'
    assert results['mad'].flagged_points == []
    assert results['z_score'].flagged_points[0].date == date(2025, 1, 31)


@pytest.mark.parametrize('count', [0, 1, 30])
def test_constant_or_empty_anomalies_do_not_crash(count):
    points = [PageviewPoint(date(2025, 1, i + 1), 0) for i in range(count)]
    for result in detect_anomalies(points).values():
        assert result.status == 'unavailable'
        assert result.flagged_points == []


def test_sensitivity_spike_changes_slope_and_keeps_source():
    spike = date(2025, 6, 15)
    sample = series(date(2025, 1, 1), date(2025, 6, 30),
                    lambda day: 100000 if day == spike else 100 + day.day % 5)
    original = deepcopy(sample)
    result = analyze_pageviews(sample)
    diagnostic = result.sensitivity
    assert diagnostic.excluded_dates == [spike]
    assert abs(diagnostic.after.ols_slope) < abs(diagnostic.before.ols_slope)
    assert diagnostic.adjusted_months[-1].adjusted
    assert not diagnostic.adjusted_months[-1].complete
    assert diagnostic.adjusted_months[-1].total_views == result.monthly_buckets[-1].total_views - 100000
    assert diagnostic.adjusted_months[-1].observed_days == 29
    assert result.monthly_buckets[-1].complete
    assert sample == original
    assert analyze_pageviews(sample) == result


def test_clean_series_sensitivity_unchanged():
    sample = series(date(2025, 1, 1), date(2025, 6, 30), lambda day: 100 + day.day % 5)
    result = analyze_pageviews(sample)
    assert result.sensitivity.excluded_dates == []
    assert result.sensitivity.before == result.sensitivity.after


def test_sensitivity_does_not_promote_incomplete_source_month():
    sample = series(date(2025, 1, 1), date(2025, 3, 31), lambda day: 100 + day.day % 5,
                    missing=[date(2025, 2, 1)])
    result = analyze_pageviews(sample)
    assert [b.month.month for b in result.sensitivity.adjusted_months] == [1, 3]


def test_unavailable_mad_means_unavailable_sensitivity():
    result = analyze_pageviews(series(date(2025, 1, 1), date(2025, 3, 31)))
    assert result.sensitivity.after.ols_slope is None
    assert result.sensitivity.warnings


def test_all_flagged_month_makes_after_unavailable():
    sample = series(date(2025, 1, 1), date(2025, 6, 30),
                    lambda day: 100000 if day.month == 6 else 100 + day.day % 5)
    result = analyze_pageviews(sample)
    assert result.sensitivity.adjusted_months[-1].total_views is None
    assert result.sensitivity.after.ols_slope is None


def test_repeated_december_peak_descriptors():
    sample = series(date(2024, 1, 1), date(2025, 12, 31), lambda day: 1000 if day.month == 12 else 100)
    seasonal = analyze_pageviews(sample).seasonality
    assert seasonal.enough_history_for_annual_comparison
    assert seasonal.month_of_year[12].average_daily_views == 1000
    assert seasonal.month_of_year[1].average_daily_views == 100
    assert seasonal.month_of_year[12].years == [2024, 2025]
    assert seasonal.month_of_year[12].contributing_months == 2


def test_one_year_is_not_repeated_year_evidence():
    result = describe_seasonality(aggregate_monthly(totals([100] * 12)))
    assert not result.enough_history_for_annual_comparison
    assert all(d.contributing_months == 1 for d in result.month_of_year.values())


def test_seasonality_equal_year_weighting_and_absent_months():
    sample = series(date(2024, 2, 1), date(2025, 2, 28), lambda day: 100 if day.year == 2024 else 200)
    sample.points = [p for p in sample.points if p.date.month == 2]
    result = describe_seasonality(aggregate_monthly(sample))
    assert result.month_of_year[2].average_daily_views == 150
    assert result.month_of_year[2].contributing_months == 2
    assert result.month_of_year[1].average_daily_views is None
    assert result.enough_history_for_annual_comparison


@pytest.mark.parametrize('shape', ['stable', 'decline', 'event', 'seasonal', 'low_volume'])
def test_realistic_regression_shapes(shape):
    def daily(day):
        index = (day.year - 2024) * 12 + day.month - 1
        if shape == 'stable':
            return 100
        if shape == 'decline':
            return 1000 - index * 30
        if shape == 'event':
            return 100000 if day == date(2025, 10, 15) else 100 + day.day % 5
        if shape == 'seasonal':
            return 1000 if day.month == 12 else 100
        return day.day % 3
    result = analyze_pageviews(series(date(2024, 1, 1), date(2025, 12, 31), daily))
    assert all(b.complete for b in result.monthly_buckets)
    if shape in ('stable', 'seasonal', 'low_volume'):
        assert result.growth.latest_3m_yoy.value == 0
    elif shape == 'decline':
        assert result.trend.ols_slope < 0 and result.trend.theil_sen_slope < 0
        assert result.growth.latest_3m_yoy.value < 0
    else:
        assert len(result.anomalies['mad'].flagged_points) == 1
        assert abs(result.sensitivity.after.ols_slope) < abs(result.sensitivity.before.ols_slope)


def test_no_data_end_to_end_and_preserved_warnings():
    sample = totals([100, 100])
    sample.points = []
    sample.status = 'no_data'
    sample.warnings = ['No upstream data']
    result = analyze_pageviews(sample)
    assert len(result.monthly_buckets) == 2
    assert all(b.total_views is None for b in result.monthly_buckets)
    assert result.growth.first_vs_last.value is None
    assert result.trend.ols_slope is None
    assert not result.seasonality.enough_history_for_annual_comparison
    assert 'No upstream data' in result.warnings
    result.warnings.append('new warning')
    assert sample.warnings == ['No upstream data']


@pytest.mark.parametrize('removed_days', [(31,), (29, 30, 31)])
@pytest.mark.parametrize('monthly_daily_increase', [0, 10])
def test_sensitivity_uses_retained_daily_averages_without_short_month_penalty(
    removed_days, monthly_daily_increase,
):
    from wikipedia_interest.models import SensitivityTrend, TrendMetrics

    excluded = [date(2025, 3, day) for day in removed_days]

    def daily(day):
        if day in excluded:
            return 10000
        baseline = 100 + monthly_daily_increase * (day.month - 1)
        # Balanced variation keeps MAD nonzero. Both exclusion sets remove
        # balanced baseline values, leaving a known exact retained-day average.
        return baseline + (0 if day.day == 31 else -1 if day.day % 2 else 1)

    sample = series(date(2025, 1, 1), date(2025, 3, 31), daily)
    original = deepcopy(sample)
    source_buckets = aggregate_monthly(sample)
    source_trend = calculate_trend(source_buckets)
    result = analyze_pageviews(sample)
    sensitivity = result.sensitivity
    assert sensitivity.excluded_dates == excluded
    assert isinstance(sensitivity.before, SensitivityTrend)
    assert isinstance(sensitivity.after, SensitivityTrend)
    assert isinstance(result.trend, TrendMetrics)
    assert sensitivity.after.input_measure == 'average_daily_views'
    assert sensitivity.after.slope_units == 'views/day per calendar month'
    assert sensitivity.after.normalization == 'mean of monthly average_daily_views'

    adjusted = sensitivity.adjusted_months[-1]
    baseline = 100 + 2 * monthly_daily_increase
    remaining = 31 - len(removed_days)
    assert adjusted.observed_days == remaining
    assert adjusted.expected_days == 31
    assert adjusted.adjusted and not adjusted.complete
    assert adjusted.total_views == baseline * remaining  # no replacement or extrapolation
    assert adjusted.average_daily_views == baseline
    assert sensitivity.after.ols_slope == pytest.approx(monthly_daily_increase)
    assert sensitivity.after.theil_sen_slope == pytest.approx(monthly_daily_increase)
    normalized = monthly_daily_increase / (100 + monthly_daily_increase)
    assert sensitivity.after.normalized_ols_slope == pytest.approx(normalized)
    assert sensitivity.after.normalized_theil_sen_slope == pytest.approx(normalized)
    # Before diagnostics use original daily averages, not the source total slope.
    expected_before = (source_buckets[-1].average_daily_views - 100) / 2
    assert sensitivity.before.ols_slope == pytest.approx(expected_before)
    before_mean = sum(b.average_daily_views for b in source_buckets) / 3
    assert sensitivity.before.normalized_ols_slope == pytest.approx(expected_before / before_mean)
    assert result.trend == source_trend
    assert result.trend.ols_slope == pytest.approx(
        (source_buckets[-1].total_views - source_buckets[0].total_views) / 2
    )
    assert result.monthly_buckets == source_buckets
    assert sample == original
