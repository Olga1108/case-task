"""Deterministic descriptive metrics over observed daily points; no network access.

See references/methodology.md for window, normalization and diagnostic conventions.
Unavailable numeric values are None, never infinity or an invented zero.
"""

from calendar import monthrange
from datetime import date
from statistics import fmean, median, pstdev, quantiles

from wikipedia_interest.models import (
    AnalysisResult, AnomalyPoint, AnomalySensitivity, AnomalySummary,
    GrowthComparison, GrowthMetrics, MonthlyBucket, MonthOfYearSummary,
    PageviewPoint, PageviewSeries, SeasonalitySummary, SensitivityTrend, TrendMetrics, WikipediaError,
)


def _index(day: date) -> int:
    return day.year * 12 + day.month - 1


def _month(index: int) -> date:
    year, month = divmod(index, 12)
    return date(year, month + 1, 1)


def _bucket(month: date, values: list[int], *, adjusted: bool = False) -> MonthlyBucket:
    expected = monthrange(month.year, month.month)[1]
    return MonthlyBucket(
        month, sum(values) if values else None,
        fmean(values) if values else None, median(values) if values else None,
        len(values), expected, len(values) == expected, adjusted,
    )


def aggregate_monthly(series: PageviewSeries) -> list[MonthlyBucket]:
    """Include every requested calendar month, even one with no observations.

    Completeness is derived from points, not status/missing_dates metadata.
    Duplicate or out-of-range points violate the validated-input contract.
    """
    groups = {i: [] for i in range(_index(series.request.start_date), _index(series.request.end_date) + 1)}
    seen = set()
    for point in series.points:
        if point.date in seen or not series.request.start_date <= point.date <= series.request.end_date:
            raise WikipediaError("INVALID_REQUEST", "Analysis requires unique points within the requested range.")
        seen.add(point.date)
        groups[_index(point.date)].append(point.views)
    return [_bucket(_month(i), values) for i, values in groups.items()]


def _comparison(old: list[date], new: list[date], lookup: dict[date, MonthlyBucket]) -> GrowthComparison:
    if not old or not new or any(m not in lookup for m in old + new):
        return GrowthComparison(None, old, new, "MISSING_OR_INCOMPLETE_MONTHS")
    previous = fmean(lookup[m].total_views for m in old)
    current = fmean(lookup[m].total_views for m in new)
    if previous == 0:
        return GrowthComparison(None, old, new, "ZERO_DENOMINATOR")
    return GrowthComparison((current - previous) / previous, old, new)


def calculate_growth(buckets: list[MonthlyBucket], start_date: date, end_date: date) -> GrowthMetrics:
    """Use complete source months only. Edge windows require nonoverlapping samples.

    Latest-three YoY is anchored to the last full calendar month in the request,
    not the last observed complete bucket, so missing months cannot shift the window.
    """
    complete = {b.month: b for b in buckets if b.complete and not b.adjusted}
    months = sorted(complete)

    def edges(size: int) -> GrowthComparison:
        if len(months) < 2 * size:
            return GrowthComparison(None, months[:size], months[-size:], "INSUFFICIENT_NONOVERLAPPING_MONTHS")
        return _comparison(months[:size], months[-size:], complete)

    yoy = {month: _comparison([month.replace(year=month.year - 1)], [month], complete) for month in months}
    last = _index(end_date) - (end_date.day < monthrange(end_date.year, end_date.month)[1])
    new = [_month(i) for i in range(last - 2, last + 1)]
    old = [month.replace(year=month.year - 1) for month in new]
    latest = _comparison(old, new, complete)
    # Explicitly retain the requested-period boundary condition even for custom buckets.
    if new[0] < start_date:
        latest = GrowthComparison(None, old, new, "MISSING_OR_INCOMPLETE_MONTHS")
    return GrowthMetrics(edges(1), edges(3), edges(6), yoy, latest)


def _trend(observations: list[tuple[date, int | float]]) -> tuple[
    float | None, float | None, float | None, float | None, list[str]
]:
    """Shared arithmetic; callers attach the appropriate input-measure record."""
    if len(observations) < 2:
        return None, None, None, None, ["INSUFFICIENT_MONTHS: at least two monthly observations are required."]
    observations = sorted(observations)
    origin = _index(observations[0][0])
    xs = [_index(month) - origin for month, _ in observations]
    ys = [views for _, views in observations]
    x_mean, y_mean = fmean(xs), fmean(ys)
    ols = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys)) / sum((x - x_mean) ** 2 for x in xs)
    robust = median([
        (ys[j] - ys[i]) / (xs[j] - xs[i])
        for i in range(len(xs)) for j in range(i + 1, len(xs))
    ])
    return (
        ols, ols / y_mean if y_mean else None,
        robust, robust / y_mean if y_mean else None,
        [] if y_mean else ["ZERO_DENOMINATOR: mean trend input is zero; normalized slopes unavailable."],
    )


def calculate_trend(buckets: list[MonthlyBucket]) -> TrendMetrics:
    """OLS and median pairwise slopes on complete, unadjusted calendar months."""
    return TrendMetrics(*_trend([(b.month, b.total_views) for b in buckets if b.complete and not b.adjusted]))


def detect_anomalies(points: list[PageviewPoint]) -> dict[str, AnomalySummary]:
    """Whole-series diagnostics, not seasonal/low-volume suitability judgments.

    Population SD; inclusive interpolated quartiles; modified z =
    0.67448975 * (value - median) / MAD. Zero scales are explicitly unavailable.
    """
    methods = ("z_score", "iqr", "mad")
    if len(points) < 2:
        return {m: AnomalySummary(m, [], "unavailable", "INSUFFICIENT_OBSERVATIONS") for m in methods}
    points = sorted(points, key=lambda point: point.date)
    values = [point.views for point in points]
    center, sd, mid = fmean(values), pstdev(values), median(values)
    q1, _, q3 = quantiles(values, n=4, method="inclusive")
    iqr = q3 - q1
    mad = median([abs(value - mid) for value in values])
    result = {}
    for method, scale in (("z_score", sd), ("iqr", iqr), ("mad", mad)):
        if scale == 0:
            result[method] = AnomalySummary(method, [], "unavailable", "ZERO_DISPERSION")
            continue
        flagged = []
        for point in points:
            score = None
            if method == "z_score":
                score = (point.views - center) / sd
                is_flagged = abs(score) > 3
            elif method == "mad":
                score = 0.67448975 * (point.views - mid) / mad
                is_flagged = abs(score) > 3.5
            else:
                is_flagged = point.views < q1 - 1.5 * iqr or point.views > q3 + 1.5 * iqr
            if is_flagged:
                flagged.append(AnomalyPoint(point.date, point.views, score))
        result[method] = AnomalySummary(method, flagged, "available")
    return result


def calculate_sensitivity(
    series: PageviewSeries, buckets: list[MonthlyBucket], mad: AnomalySummary,
) -> AnomalySensitivity:
    """Rebuild originally complete months only, without imputing excluded days.

    Before/after fits use monthly daily averages, normalized by their own mean.
    Retained-day totals remain audit data only, not the adjusted trend input.
    An unavailable MAD diagnostic makes the after trend unavailable as well.
    """
    before = SensitivityTrend(*_trend([
        (b.month, b.average_daily_views) for b in buckets if b.complete and not b.adjusted
    ]))
    if mad.status == "unavailable":
        warning = f"MAD exclusion unavailable: {mad.reason}."
        return AnomalySensitivity(before, SensitivityTrend(warnings=[warning]), [], [], [warning])
    groups = {b.month: [] for b in buckets if b.complete and not b.adjusted}
    excluded = {point.date for point in mad.flagged_points}
    used_exclusions = []
    for point in sorted(series.points, key=lambda point: point.date):
        month = point.date.replace(day=1)
        if month in groups:
            if point.date in excluded:
                used_exclusions.append(point.date)
            else:
                groups[month].append(point.views)
    adjusted = [_bucket(month, values, adjusted=True) for month, values in groups.items()]
    warnings = [
        "Sensitivity before/after slopes use monthly daily averages (views/day per calendar month), "
        "not headline monthly totals. Each fit is normalized by its own mean daily-average input.",
        "Adjusted totals are audit-only retained-day sums; no imputation or extrapolation.",
    ]
    if any(b.observed_days == 0 for b in adjusted):
        after = SensitivityTrend(warnings=["An originally complete month has no remaining observations."])
        warnings.append("After trend unavailable to avoid silently changing the compared month set.")
    else:
        after = SensitivityTrend(*_trend([(b.month, b.average_daily_views) for b in adjusted]))
    return AnomalySensitivity(before, after, adjusted, used_exclusions, warnings)


def describe_seasonality(buckets: list[MonthlyBucket]) -> SeasonalitySummary:
    """Unweighted mean of per-year monthly daily averages; no seasonal classifier."""
    descriptors = {}
    for month in range(1, 13):
        matching = [b for b in buckets if b.complete and not b.adjusted and b.month.month == month]
        descriptors[month] = MonthOfYearSummary(
            fmean(b.average_daily_views for b in matching) if matching else None,
            len(matching), sorted({b.month.year for b in matching}),
        )
    enough = any(len(value.years) >= 2 for value in descriptors.values())
    warnings = ["Month-of-year averages are descriptive and may also reflect long-term change or events."]
    if not enough:
        warnings.append("No calendar month has complete observations in at least two distinct years.")
    return SeasonalitySummary(descriptors, enough, warnings)


def analyze_pageviews(series: PageviewSeries) -> AnalysisResult:
    """Calculate deterministic evidence only; preserve input points and warnings."""
    buckets = aggregate_monthly(series)
    anomalies = detect_anomalies(series.points)
    warnings = list(series.warnings)
    if any(not bucket.complete for bucket in buckets):
        warnings.append("Incomplete months remain visible but are excluded from source growth and trend metrics.")
    warnings.append("Anomaly flags are unadjusted diagnostics; seasonal patterns and low-volume data may affect them.")
    return AnalysisResult(
        buckets, calculate_growth(buckets, series.request.start_date, series.request.end_date),
        calculate_trend(buckets), anomalies, calculate_sensitivity(series, buckets, anomalies["mad"]),
        describe_seasonality(buckets), warnings,
    )
