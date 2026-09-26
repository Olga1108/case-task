"""Compact evidence plus shared deterministic direction interpretation."""

from typing import Literal, TypedDict

from wikipedia_interest.models import GrowthComparison, LanguageResearchResult, ResearchResult


DirectionStatus = Literal[
    "positive", "negative", "flat", "mixed", "inconclusive", "unavailable",
]


class DirectionSummary(TypedDict):
    status: DirectionStatus
    summary: str


def _sign(value: float | None) -> int | None:
    if value is None:
        return None
    return 1 if value > 0 else -1 if value < 0 else 0


def _long_range_description(sign: int | None) -> str:
    return {
        1: "positive",
        -1: "negative",
        0: "flat",
        None: "unavailable",
    }[sign]


def build_direction_summary(language: LanguageResearchResult) -> DirectionSummary:
    """Return the report's deterministic direction conclusion without mutation."""
    if language.analysis is None:
        return {
            "status": "unavailable",
            "summary": "Direction unavailable: no analyzed source series.",
        }

    analysis = language.analysis
    yoy_sign = _sign(analysis.growth.latest_3m_yoy.value)
    trend_sign = _sign(analysis.trend.normalized_theil_sen_slope)
    if yoy_sign is None:
        long_range = _long_range_description(trend_sign)
        return {
            "status": "inconclusive",
            "summary": (
                "Recent direction is inconclusive because latest-3m YoY is unavailable; "
                f"long-range trend is {long_range}."
            ),
        }
    if trend_sign is None:
        return {
            "status": "inconclusive",
            "summary": "Direction inconclusive: robust trend is unavailable.",
        }

    sensitivity = analysis.sensitivity
    if sensitivity.excluded_dates:
        after_sign = _sign(sensitivity.after.normalized_theil_sen_slope)
        if after_sign is None or after_sign != trend_sign:
            return {
                "status": "inconclusive",
                "summary": (
                    "Direction inconclusive: anomaly sensitivity does not support "
                    "the headline trend."
                ),
            }

    if yoy_sign == trend_sign == 1:
        return {
            "status": "positive",
            "summary": "Recent YoY and robust long-range trend are both positive.",
        }
    if yoy_sign == trend_sign == -1:
        return {
            "status": "negative",
            "summary": "Recent YoY and robust long-range trend are both negative.",
        }
    if yoy_sign == trend_sign == 0:
        return {
            "status": "flat",
            "summary": "Recent YoY and robust long-range trend are both flat.",
        }
    return {
        "status": "mixed",
        "summary": "Recent YoY and robust long-range trend point in different directions.",
    }


def _comparison(value: GrowthComparison) -> dict:
    return {
        "value": value.value,
        "old_months": [day.isoformat() for day in value.old_months],
        "new_months": [day.isoformat() for day in value.new_months],
        "reason": value.reason,
    }


def build_agent_summary(result: ResearchResult) -> dict:
    """Return JSON-ready evidence in requested language order without mutation.

    All warning text lives once in top-level warnings. warning_ids at each scope
    are zero-based indexes into that list, including shared messages across
    languages. top-level warning_ids identifies research/topic warnings.
    Growth values are fractions; unavailable evidence is null with reasons or
    warning references. Samples are bounded, not complete observation exports.
    """
    warnings = []

    def warning_ids(messages):
        ids = []
        for message in messages:
            if message not in warnings:
                warnings.append(message)
            index = warnings.index(message)
            if index not in ids:
                ids.append(index)
        return ids

    topic = result.topic
    summary = {
        "topic": {"query": topic.original_query, "wikidata_id": topic.wikidata_id,
                  "selected_article": topic.selected_candidate.article_title,
                  "query_language": topic.query_language},
        "period": {"start": result.start_date.isoformat(), "end": result.end_date.isoformat()},
        "workflow_status": result.status,
        "languages": [],
        "warnings": warnings,
        "warning_ids": warning_ids(result.warnings + topic.warnings + topic.selected_candidate.warnings),
    }
    for language in result.languages:
        series, analysis = language.pageviews, language.analysis
        item = {
            "language": language.language, "project": language.project,
            "article": language.article_title, "mapping_status": language.mapping_status,
            "workflow_status": language.status,
            "direction": build_direction_summary(language),
            "data": None, "growth": None, "trend": None, "anomalies": None,
            "sensitivity": None, "seasonality": None,
            "warning_ids": warning_ids(language.warnings), "error": None,
        }
        if language.error is not None:
            error = language.error
            item["error"] = {"code": error.code, "message": str(error)}
            for name in ("http_status", "retry_after"):
                if getattr(error, name) is not None:
                    item["error"][name] = getattr(error, name)
        if series is not None:
            days = [point.date for point in series.points]
            buckets = analysis.monthly_buckets if analysis else None
            item["data"] = {
                "status": series.status,
                "observed_start": min(days).isoformat() if days else None,
                "observed_end": max(days).isoformat() if days else None,
                "observation_count": len(days), "missing_day_count": len(series.missing_dates),
                "zero_day_count": sum(point.views == 0 for point in series.points),
                "complete_months": sum(b.complete and not b.adjusted for b in buckets) if buckets is not None else None,
                "incomplete_months": sum(not b.complete and not b.adjusted for b in buckets) if buckets is not None else None,
                "warning_ids": warning_ids(series.warnings),
            }
        if analysis is not None:
            item["warning_ids"] = warning_ids(language.warnings + analysis.warnings)
            growth = analysis.growth
            available = [(month, value) for month, value in sorted(growth.same_month_yoy.items())
                         if value.value is not None]
            item["growth"] = {
                "units": "fractional change",
                "latest_3m_yoy": _comparison(growth.latest_3m_yoy),
                "same_month_yoy": [_comparison(value) for _, value in available[-6:]],
            }
            trend = analysis.trend
            item["trend"] = {
                "input_measure": "complete source monthly total_views",
                "slope_units": "monthly views per calendar month",
                "normalization": "mean monthly total_views",
                "normalized_slope_units": "fraction per calendar month",
                "theil_sen_slope": trend.theil_sen_slope,
                "normalized_theil_sen_slope": trend.normalized_theil_sen_slope,
                "normalized_ols_slope": trend.normalized_ols_slope,
                "warning_ids": warning_ids(trend.warnings),
            }
            item["anomalies"] = {}
            for method, diagnostic in sorted(analysis.anomalies.items()):
                record = {"status": diagnostic.status, "flagged_count": len(diagnostic.flagged_points),
                          "reason": diagnostic.reason}
                if method == "mad":
                    record["largest_examples"] = [
                        {"date": point.date.isoformat(), "views": point.views}
                        for point in sorted(diagnostic.flagged_points, key=lambda p: (-p.views, p.date))[:5]
                    ]
                item["anomalies"][method] = record
            sensitivity = analysis.sensitivity
            item["sensitivity"] = {
                "input_measure": sensitivity.before.input_measure,
                "slope_units": sensitivity.before.slope_units,
                "normalization": sensitivity.before.normalization + " (each fit separately)",
                "normalized_slope_units": "fraction per calendar month",
                "excluded_observation_count": len(sensitivity.excluded_dates),
                "warning_ids": warning_ids(sensitivity.warnings),
            }
            for name in ("before", "after"):
                diagnostic = getattr(sensitivity, name)
                item["sensitivity"][name] = {
                    "normalized_theil_sen_slope": diagnostic.normalized_theil_sen_slope,
                    "normalized_ols_slope": diagnostic.normalized_ols_slope,
                    "warning_ids": warning_ids(diagnostic.warnings),
                }
            seasonality = analysis.seasonality
            item["seasonality"] = {
                "enough_history_for_annual_comparison": seasonality.enough_history_for_annual_comparison,
                "month_of_year": [
                    {"month": month, "average_daily_views": value.average_daily_views,
                     "contributing_months": value.contributing_months, "years": list(value.years)}
                    for month, value in sorted(seasonality.month_of_year.items())
                ],
                "warning_ids": warning_ids(seasonality.warnings),
            }
        summary["languages"].append(item)
    return summary
