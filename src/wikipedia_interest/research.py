"""Thin application workflow for an explicitly selected and mapped topic."""

from contextlib import nullcontext
from datetime import date
import math

import httpx

from wikipedia_interest.analysis import analyze_pageviews
from wikipedia_interest.models import (
    LanguageResearchResult, PageviewRequest, ResearchResult, ResolvedTopic,
    TopicCandidate, WikipediaError,
)
from wikipedia_interest.wikipedia_client import fetch_pageviews


def research_topic(
    resolved_topic: ResolvedTopic, start_date: date, end_date: date, *,
    user_agent: str, timeout: float = 10.0, client: httpx.Client | None = None,
) -> ResearchResult:
    """Fetch and analyze mapped articles in their requested order, without retries.

    Shared invalid input raises WikipediaError before HTTP. Per-language domain
    failures are retained and other languages continue. Unexpected programming
    errors propagate rather than being disguised as upstream failures.

    A language succeeds operationally when analysis exists, including no_data and
    partial_data: these preserve their series and are not evidence-quality labels.
    Overall completed/partial/failed means all/some/none reached analysis. An
    unresolved topic with an explicitly validated selection and failed mappings
    is accepted so each mapping failure remains visible.

    A supplied client stays open; otherwise one client is owned for the operation.
    No topic discovery, validation HTTP, or replacement search is performed here.
    """
    if (
        not isinstance(resolved_topic, ResolvedTopic)
        or not isinstance(resolved_topic.selected_candidate, TopicCandidate)
        or resolved_topic.selected_candidate.status != "valid"
        or not resolved_topic.wikidata_id
        or resolved_topic.selected_candidate.wikidata_id != resolved_topic.wikidata_id
        or not resolved_topic.language_mappings
    ):
        raise WikipediaError("INVALID_REQUEST", "Supply an explicitly validated selection and language mappings.")
    if type(start_date) is not date or type(end_date) is not date:
        raise WikipediaError("INVALID_REQUEST", "Boundaries must be datetime.date objects.")
    if start_date > end_date or start_date < date(2015, 7, 1):
        raise WikipediaError("INVALID_REQUEST", "Use an ordered range starting on or after 2015-07-01.")
    if (not isinstance(user_agent, str) or not user_agent.strip() or not user_agent.isascii()
            or any(ord(c) < 32 or ord(c) == 127 for c in user_agent)):
        raise WikipediaError("INVALID_REQUEST", "Supply a nonempty printable ASCII User-Agent with app/contact information.")
    if type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0:
        raise WikipediaError("INVALID_REQUEST", "Timeout must be a positive finite number.")

    results = []
    with nullcontext(client) if client is not None else httpx.Client() as http:
        for mapping in resolved_topic.language_mappings:
            result = LanguageResearchResult(
                mapping.language, mapping.project, mapping.article_title, mapping.status,
                "mapping_unavailable", warnings=list(mapping.warnings),
            )
            results.append(result)
            if mapping.status != "valid":
                result.error = mapping.error or WikipediaError(mapping.status, "Requested language mapping is unavailable.")
                continue
            if mapping.wikidata_id != resolved_topic.wikidata_id:
                result.error = WikipediaError("TOPIC_MAPPING_MISMATCH", "Mapping identity differs from the selected topic.")
                continue
            try:
                request = PageviewRequest(mapping.project, mapping.article_title, start_date, end_date)
                result.status = "retrieval_failed"
                result.pageviews = fetch_pageviews(request, user_agent=user_agent, timeout=timeout, client=http)
                result.warnings.extend(result.pageviews.warnings)
                result.status = "analysis_failed"
                result.analysis = analyze_pageviews(result.pageviews)
                # Analysis already carries pageview warnings; retain each message once.
                for warning in result.analysis.warnings:
                    if warning not in result.warnings:
                        result.warnings.append(warning)
                result.status = {
                    "complete": "completed", "partial": "partial_data", "no_data": "no_data",
                }[result.pageviews.status]
            except WikipediaError as exc:
                result.error = exc
    successful = sum(result.analysis is not None for result in results)
    status = "completed" if successful == len(results) else "partial" if successful else "failed"
    warnings = list(resolved_topic.warnings)
    if status != "completed":
        warnings.append("Some requested languages did not reach analysis; see per-language states.")
    return ResearchResult(resolved_topic, start_date, end_date, results, status, warnings)
