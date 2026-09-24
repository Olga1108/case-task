"""Pageview and topic-resolution records."""

from dataclasses import dataclass, field
from datetime import date, datetime
import re
from typing import Literal


class WikipediaError(ValueError):
    """A retrieval failure with a machine-readable code and optional HTTP details."""

    def __init__(
        self, code: str, message: str, *, http_status: int | None = None,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.retry_after = retry_after


# Keep the first retrieval slice's public exception name compatible.
PageviewError = WikipediaError


@dataclass(frozen=True)
class PageviewRequest:
    """Inclusive UTC date range for one unencoded Wikipedia article title.

    Only daily retrieval is supported in this implementation. Project validation
    checks domain syntax, not whether a language edition exists.
    """

    project: str
    article_title: str
    start_date: date
    end_date: date
    granularity: str = "daily"
    access: str = "all-access"
    agent: str = "user"

    def __post_init__(self) -> None:
        if not isinstance(self.project, str) or not re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*\.wikipedia\.org", self.project
        ):
            raise PageviewError("INVALID_REQUEST", "Use a project such as uk.wikipedia.org.")
        if (
            not isinstance(self.article_title, str)
            or not self.article_title.strip()
            or any(ord(char) < 32 or ord(char) == 127 for char in self.article_title)
        ):
            raise PageviewError("INVALID_REQUEST", "Article title must be nonempty text without controls.")
        if type(self.start_date) is not date or type(self.end_date) is not date:
            raise PageviewError("INVALID_REQUEST", "Boundaries must be datetime.date objects.")
        if self.start_date > self.end_date or self.start_date < date(2015, 7, 1):
            raise PageviewError("INVALID_REQUEST", "Use an ordered range starting on or after 2015-07-01.")
        if self.granularity != "daily":
            raise PageviewError("INVALID_REQUEST", "Only daily granularity is currently supported.")
        if self.access not in ("all-access", "desktop", "mobile-web", "mobile-app"):
            raise PageviewError("INVALID_REQUEST", "Unsupported access filter.")
        if self.agent not in ("all-agents", "user", "spider", "automated"):
            raise PageviewError("INVALID_REQUEST", "Unsupported agent filter.")


@dataclass(frozen=True)
class PageviewPoint:
    """One observed UTC day; zero is valid, absent observations are not points."""

    date: date
    views: int

    def __post_init__(self) -> None:
        if type(self.date) is not date:
            raise PageviewError("INVALID_REQUEST", "Point date must be a datetime.date object.")
        if type(self.views) is not int or self.views < 0:
            raise PageviewError("INVALID_REQUEST", "Views must be a non-negative integer.")


@dataclass
class PageviewSeries:
    """Validated observations; complete describes date coverage, not topic coverage."""

    request: PageviewRequest
    points: list[PageviewPoint]
    missing_dates: list[date]
    status: Literal["complete", "partial", "no_data"]
    retrieved_at: datetime
    warnings: list[str] = field(default_factory=list)


@dataclass
class TopicCandidate:
    """Page evidence, not a semantic selection or confidence assessment.

    status is 'valid' or a domain failure code. A valid page has a Q-ID and is
    neither a disambiguation page nor a section redirect. Search rank is 1-based.
    """

    source_language: str
    input_title: str
    article_title: str | None = None
    page_id: int | None = None
    canonical_url: str | None = None
    wikidata_id: str | None = None
    snippet: str | None = None
    search_rank: int | None = None
    search_page_id: int | None = None
    is_disambiguation: bool = False
    redirect_chain: list[str] = field(default_factory=list)
    redirect_fragment: str | None = None
    status: str = "unvalidated"
    warnings: list[str] = field(default_factory=list)
    error: WikipediaError | None = None


@dataclass
class LanguageMapping:
    """One requested edition: 'valid' or an explicit failure code."""

    language: str
    project: str
    status: str
    sitelink_title: str | None = None
    article_title: str | None = None
    page_id: int | None = None
    canonical_url: str | None = None
    wikidata_id: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    redirect_fragment: str | None = None
    warnings: list[str] = field(default_factory=list)
    error: WikipediaError | None = None


@dataclass
class ResolvedTopic:
    """Structural mapping of an explicitly selected candidate, not a recommendation."""

    original_query: str
    query_language: str
    wikidata_id: str
    status: Literal["resolved", "partial", "unresolved"]
    selected_candidate: TopicCandidate
    language_mappings: list[LanguageMapping]
    warnings: list[str] = field(default_factory=list)


@dataclass
class MonthlyBucket:
    """Observed values only; month is its first day, empty totals are unavailable."""

    month: date
    total_views: int | None
    average_daily_views: float | None
    median_daily_views: float | None
    observed_days: int
    expected_days: int
    complete: bool
    adjusted: bool = False


@dataclass
class GrowthComparison:
    """Relative change (0.1 means 10%) with auditable comparison windows."""

    value: float | None
    old_months: list[date]
    new_months: list[date]
    reason: str | None = None


@dataclass
class GrowthMetrics:
    first_vs_last: GrowthComparison
    first_3m_vs_last_3m: GrowthComparison
    first_6m_vs_last_6m: GrowthComparison
    same_month_yoy: dict[date, GrowthComparison]
    latest_3m_yoy: GrowthComparison


@dataclass
class TrendMetrics:
    """Slopes per calendar month; both normalized slopes use mean monthly totals."""

    ols_slope: float | None = None
    normalized_ols_slope: float | None = None
    theil_sen_slope: float | None = None
    normalized_theil_sen_slope: float | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class AnomalyPoint:
    date: date
    views: int
    score: float | None = None


@dataclass
class AnomalySummary:
    method: str
    flagged_points: list[AnomalyPoint]
    status: Literal["available", "unavailable"]
    reason: str | None = None


@dataclass
class SensitivityTrend:
    """Trend of monthly daily averages, before or after diagnostic exclusion.

    Raw slopes measure change in views/day per calendar month. Normalization
    divides by the unweighted mean of the monthly daily averages used in that
    fit. Raw slopes must not be compared to headline monthly-total slopes.
    """

    ols_slope: float | None = None
    normalized_ols_slope: float | None = None
    theil_sen_slope: float | None = None
    normalized_theil_sen_slope: float | None = None
    warnings: list[str] = field(default_factory=list)
    input_measure: Literal["average_daily_views"] = field(default="average_daily_views", init=False)
    slope_units: str = field(default="views/day per calendar month", init=False)
    normalization: str = field(default="mean of monthly average_daily_views", init=False)


@dataclass
class AnomalySensitivity:
    before: SensitivityTrend
    after: SensitivityTrend
    adjusted_months: list[MonthlyBucket]
    excluded_dates: list[date]
    warnings: list[str] = field(default_factory=list)


@dataclass
class MonthOfYearSummary:
    average_daily_views: float | None
    contributing_months: int
    years: list[int]


@dataclass
class SeasonalitySummary:
    month_of_year: dict[int, MonthOfYearSummary]
    enough_history_for_annual_comparison: bool
    warnings: list[str] = field(default_factory=list)


@dataclass
class AnalysisResult:
    monthly_buckets: list[MonthlyBucket]
    growth: GrowthMetrics
    trend: TrendMetrics
    anomalies: dict[str, AnomalySummary]
    sensitivity: AnomalySensitivity
    seasonality: SeasonalitySummary
    warnings: list[str] = field(default_factory=list)


@dataclass
class LanguageResearchResult:
    """Workflow state is independent of data completeness and evidence quality."""

    language: str
    project: str
    article_title: str | None
    mapping_status: str
    status: Literal[
        "mapping_unavailable", "retrieval_failed", "analysis_failed",
        "no_data", "partial_data", "completed",
    ]
    pageviews: PageviewSeries | None = None
    analysis: AnalysisResult | None = None
    error: WikipediaError | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class ResearchResult:
    """Completed means all languages reached analysis, including no_data results."""

    topic: ResolvedTopic
    start_date: date
    end_date: date
    languages: list[LanguageResearchResult]
    status: Literal["completed", "partial", "failed"]
    warnings: list[str] = field(default_factory=list)
