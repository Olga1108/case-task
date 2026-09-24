"""Explicit candidate discovery and structural cross-language mapping.

No candidate selection, translation, or caching. Transient HTTP failures use a
small retry budget. Public functions accept an optional caller-owned HTTPX client;
otherwise each operation closes its client.
Language arguments are Wikipedia edition subdomains (e.g. en, pl, cs, uk).
Langlinks are matched by their official URL host, not guessed from language codes.
"""

from contextlib import nullcontext
from html.parser import HTMLParser
import math
import re
import time
from urllib.parse import urlsplit

import httpx

from wikipedia_interest.models import (
    LanguageMapping, ResolvedTopic, TopicCandidate, WikipediaError,
)

_MAX_ATTEMPTS = 3
_MAX_RETRY_DELAY = 5.0


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        raise WikipediaError("INVALID_REQUEST", f"{label} must be nonempty text without controls.")
    return value


def _project(language: str) -> str:
    if not isinstance(language, str) or not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", language):
        raise WikipediaError("INVALID_REQUEST", "Use a Wikipedia edition code such as pl or cs.")
    return f"{language}.wikipedia.org"


def _configuration(user_agent: str, timeout: float) -> None:
    _text(user_agent, "User-Agent")
    if not user_agent.isascii() or "\x7f" in user_agent:
        raise WikipediaError("INVALID_REQUEST", "User-Agent must be printable ASCII with app/contact information.")
    if type(timeout) not in (float, int) or not math.isfinite(timeout) or timeout <= 0:
        raise WikipediaError("INVALID_REQUEST", "Timeout must be a positive finite number.")


def _invalid(message: str) -> WikipediaError:
    return WikipediaError("INVALID_API_RESPONSE", message)


def _url_host(value: object) -> str:
    if not isinstance(value, str):
        raise _invalid("Expected a URL string.")
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise _invalid("Malformed URL in API metadata.") from exc
    if parsed.scheme != "https" or not parsed.netloc:
        raise _invalid("Expected an absolute HTTPS URL in API metadata.")
    return parsed.netloc


def _retry_delay(retry_after: str | None, attempt: int) -> float | None:
    """Return a bounded delay, or None when a server delay is too long."""
    if retry_after is not None:
        try:
            delay = float(retry_after)
        except ValueError:
            delay = 2 ** (attempt - 1)
        else:
            if not math.isfinite(delay) or delay < 0:
                delay = 2 ** (attempt - 1)
            elif delay > _MAX_RETRY_DELAY:
                return None
        return min(delay, _MAX_RETRY_DELAY)
    return min(2 ** (attempt - 1), _MAX_RETRY_DELAY)


def _wait_to_retry(retry_after: str | None, attempt: int) -> bool:
    if attempt >= _MAX_ATTEMPTS:
        return False
    delay = _retry_delay(retry_after, attempt)
    if delay is None:
        return False
    time.sleep(delay)
    return True


def _get(http: httpx.Client, host: str, params: dict, user_agent: str, timeout: float) -> dict:
    """Action API GET with bounded retries for transient upstream failures."""
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            response = http.get(
                f"https://{host}/w/api.php",
                params={**params, "format": "json", "formatversion": 2, "maxlag": 5},
                headers={"User-Agent": user_agent, "Accept": "application/json"},
                timeout=timeout, follow_redirects=False,
            )
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            if _wait_to_retry(None, attempt):
                continue
            raise WikipediaError("API_UNAVAILABLE", "Wikipedia request failed or timed out.") from exc
        except httpx.RequestError as exc:
            raise WikipediaError("API_UNAVAILABLE", "Wikipedia request failed or timed out.") from exc
        status = response.status_code
        retry_after = response.headers.get("Retry-After")
        if status != 200:
            code = "UNEXPECTED_HTTP_STATUS"
            if status == 429:
                code = "RATE_LIMITED"
            elif status >= 500:
                code = "API_UNAVAILABLE"
            elif status in (401, 403):
                code = "ACCESS_BLOCKED"
            elif status == 400:
                code = "INVALID_REQUEST"
            failure = WikipediaError(code, f"Action API returned HTTP {status}.",
                                     http_status=status, retry_after=retry_after)
            if (status == 429 or 500 <= status < 600) and _wait_to_retry(retry_after, attempt):
                continue
            raise failure
        try:
            payload = response.json()
        except ValueError as exc:
            raise _invalid("Action API returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise _invalid("Expected an Action API object.")
        if "error" in payload:
            error = payload["error"]
            if not isinstance(error, dict) or not isinstance(error.get("code"), str):
                raise _invalid("Malformed Action API error.")
            upstream = error["code"]
            code = {
                "ratelimited": "RATE_LIMITED", "maxlag": "API_UNAVAILABLE",
                "readonly": "API_UNAVAILABLE", "permissiondenied": "ACCESS_BLOCKED",
                "readapidenied": "ACCESS_BLOCKED", "badvalue": "INVALID_REQUEST",
            }.get(upstream, "API_UNAVAILABLE")
            failure = WikipediaError(
                code, f"Action API error {upstream}: {error.get('info', '')}",
                http_status=status, retry_after=retry_after,
            )
            if upstream == "maxlag" and _wait_to_retry(retry_after, attempt):
                continue
            raise failure
        # An ignored parameter could undermine validation; do not silently accept it.
        if payload.get("warnings"):
            raise _invalid(f"Action API reported warnings: {payload['warnings']}")
        return payload
    raise AssertionError("Retry loop exhausted without returning or raising.")


class _PlainText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in ("br", "p", "div"):
            self.parts.append(" ")


def _plain(snippet: object) -> str | None:
    if snippet is None:
        return None
    if not isinstance(snippet, str):
        raise _invalid("Search snippet must be text.")
    parser = _PlainText()
    parser.feed(snippet)
    parser.close()
    return " ".join("".join(parser.parts).split())


def _reject(candidate: TopicCandidate, code: str, message: str) -> TopicCandidate:
    candidate.status = code
    candidate.error = WikipediaError(code, message)
    candidate.warnings.append(message)
    return candidate


def _page(http: httpx.Client, title: str, language: str, user_agent: str, timeout: float) -> TopicCandidate:
    _text(title, "Article title")
    if "|" in title or "#" in title:
        raise WikipediaError("INVALID_REQUEST", "Supply one whole-page title, without a fragment or pipe.")
    project = _project(language)
    payload = _get(http, project, {
        "action": "query", "titles": title, "redirects": 1,
        "prop": "pageprops|info", "inprop": "url",
    }, user_agent, timeout)
    query = payload.get("query")
    if not isinstance(query, dict):
        raise _invalid("Missing query object.")
    candidate = TopicCandidate(language, title)
    if query.get("interwiki"):
        return _reject(candidate, "REDIRECT_UNRESOLVED", "Interwiki targets are not article mappings.")
    pages = query.get("pages")
    if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
        raise _invalid("Expected exactly one page record.")
    page = pages[0]
    if not isinstance(page.get("title"), str) or not page["title"]:
        raise _invalid("Missing page title.")
    candidate.article_title = page["title"]
    # Validate the returned title against the documented normalization/redirect chain.
    current = title
    for key in ("normalized", "redirects"):
        transitions = query.get(key, [])
        if not isinstance(transitions, list):
            raise _invalid(f"Malformed {key} list.")
        for transition in transitions:
            if (not isinstance(transition, dict)
                    or not isinstance(transition.get("from"), str)
                    or not isinstance(transition.get("to"), str)
                    or transition["from"] != current):
                raise _invalid(f"Unexpected {key} mapping.")
            current = transition["to"]
            if key == "redirects":
                if not candidate.redirect_chain:
                    candidate.redirect_chain.append(transition["from"])
                candidate.redirect_chain.append(current)
                fragment = transition.get("tofragment")
                if fragment is not None and not isinstance(fragment, str):
                    raise _invalid("Malformed redirect fragment.")
                candidate.redirect_fragment = fragment or candidate.redirect_fragment
    if current != page["title"]:
        raise _invalid("Returned page does not match the requested title or its redirects.")
    if "missing" in page:
        return _reject(candidate, "ARTICLE_NOT_FOUND", "MediaWiki reports the page is missing.")
    if "invalid" in page:
        return _reject(candidate, "INVALID_REQUEST", "MediaWiki reports an invalid title.")
    if type(page.get("pageid")) is not int or page["pageid"] <= 0 or type(page.get("ns")) is not int:
        raise _invalid("Invalid page ID or namespace.")
    candidate.page_id = page["pageid"]
    url = page.get("canonicalurl", page.get("fullurl"))
    if url is not None:
        if _url_host(url) != project:
            raise _invalid("Invalid canonical Wikipedia URL.")
        candidate.canonical_url = url
    props = page.get("pageprops", {})
    if not isinstance(props, dict):
        raise _invalid("Malformed page properties.")
    qid = props.get("wikibase_item")
    if qid is not None and (not isinstance(qid, str) or not re.fullmatch(r"Q[1-9][0-9]*", qid)):
        raise _invalid("Malformed Wikidata Q-ID.")
    candidate.wikidata_id = qid
    candidate.is_disambiguation = "disambiguation" in props
    if page["ns"] != 0:
        return _reject(candidate, "NON_MAIN_NAMESPACE", "Only main-namespace articles are supported.")
    if "redirect" in page:
        return _reject(candidate, "REDIRECT_UNRESOLVED", "Redirect did not resolve to an article.")
    if candidate.redirect_fragment:
        return _reject(candidate, "TOPIC_MAPPING_MISMATCH", "Section redirects do not represent whole-page topics.")
    if candidate.is_disambiguation:
        return _reject(candidate, "DISAMBIGUATION_PAGE", "Select a specific topic instead of a disambiguation page.")
    if qid is None:
        return _reject(candidate, "WIKIDATA_ITEM_MISSING", "The page has no Wikidata identity.")
    candidate.status = "valid"
    return candidate


def validate_topic_candidate(
    selected: TopicCandidate | str, language: str, *, user_agent: str,
    timeout: float = 10.0, client: httpx.Client | None = None,
) -> TopicCandidate:
    """Re-fetch canonical evidence. Semantic rejection returns status/error on the record.

    Transport/API/invalid-input failures raise WikipediaError. Candidate discovery
    context is retained when passed a candidate instead of a title.
    """
    _configuration(user_agent, timeout)
    if isinstance(selected, TopicCandidate) and selected.source_language != language:
        raise WikipediaError("INVALID_REQUEST", "Candidate language does not match requested edition.")
    title = selected.input_title if isinstance(selected, TopicCandidate) else selected
    with nullcontext(client) if client is not None else httpx.Client() as http:
        result = _page(http, title, language, user_agent, timeout)
    if isinstance(selected, TopicCandidate):
        result.snippet = selected.snippet
        result.search_rank = selected.search_rank
        result.search_page_id = selected.search_page_id
        if selected.wikidata_id and result.status == "valid" and selected.wikidata_id != result.wikidata_id:
            _reject(result, "TOPIC_MAPPING_MISMATCH", "Candidate Wikidata identity changed since discovery.")
    return result


def search_topic_candidates(
    query: str, query_language: str, *, user_agent: str, limit: int = 5,
    timeout: float = 10.0, client: httpx.Client | None = None,
) -> list[TopicCandidate]:
    """Return at most five ranked candidates; [] means no search matches.

    Multiple results are not TOPIC_AMBIGUOUS: semantic selection belongs to the
    agent/user. Failed enrichment is retained on each candidate with its error.
    """
    _configuration(user_agent, timeout)
    _text(query, "Query")
    project = _project(query_language)
    if type(limit) is not int or not 1 <= limit <= 5:
        raise WikipediaError("INVALID_REQUEST", "Candidate limit must be between 1 and 5.")
    with nullcontext(client) if client is not None else httpx.Client() as http:
        payload = _get(http, project, {
            "action": "query", "list": "search", "srsearch": query,
            "srnamespace": 0, "srlimit": limit,
        }, user_agent, timeout)
        body = payload.get("query")
        if not isinstance(body, dict) or not isinstance(body.get("search"), list):
            raise _invalid("Expected a search result list.")
        candidates = []
        for rank, hit in enumerate(body["search"][:limit], 1):
            if (not isinstance(hit, dict) or not isinstance(hit.get("title"), str)
                    or not hit["title"] or type(hit.get("pageid")) is not int
                    or hit["pageid"] <= 0 or hit.get("ns") != 0):
                raise _invalid("Malformed search result.")
            try:
                candidate = _page(http, hit["title"], query_language, user_agent, timeout)
            except WikipediaError as exc:
                candidate = TopicCandidate(query_language, hit["title"], status=exc.code,
                                           error=exc, warnings=[str(exc)])
            candidate.search_rank = rank
            candidate.search_page_id = hit["pageid"]
            candidate.snippet = _plain(hit.get("snippet"))
            candidates.append(candidate)
        return candidates


def _langlinks(
    http: httpx.Client, source: TopicCandidate, user_agent: str, timeout: float,
) -> dict[str, dict]:
    """Retrieve all interlanguage links for one already validated source page."""
    params = {
        "action": "query", "titles": source.article_title, "prop": "langlinks",
        "llprop": "url", "lllimit": "max",
    }
    links: dict[str, dict] = {}
    seen_continuations = set()
    while True:
        payload = _get(http, _project(source.source_language), params, user_agent, timeout)
        query = payload.get("query")
        pages = query.get("pages") if isinstance(query, dict) else None
        if not isinstance(pages, list) or len(pages) != 1 or not isinstance(pages[0], dict):
            raise _invalid("Expected exactly one source page with language links.")
        page = pages[0]
        if page.get("pageid") != source.page_id or page.get("title") != source.article_title:
            raise _invalid("Language links response does not match the validated source page.")
        page_links = page.get("langlinks", [])
        if not isinstance(page_links, list):
            raise _invalid("Malformed language links list.")
        for link in page_links:
            if (not isinstance(link, dict) or not isinstance(link.get("lang"), str)
                    or not isinstance(link.get("title"), str) or not link["title"]
                    or not isinstance(link.get("url"), str)):
                raise _invalid("Malformed language link.")
            language = link["lang"]
            if language in links:
                raise _invalid("Duplicate language link.")
            links[language] = link
        continuation = payload.get("continue")
        if continuation is None:
            return links
        if (not isinstance(continuation, dict)
                or set(continuation) != {"continue", "llcontinue"}
                or not all(isinstance(value, str) for value in continuation.values())):
            raise _invalid("Malformed language links continuation.")
        marker = (continuation["continue"], continuation["llcontinue"])
        if marker in seen_continuations:
            raise _invalid("Repeated language links continuation.")
        seen_continuations.add(marker)
        params = params | continuation


def map_topic_languages(
    original_query: str, selected: TopicCandidate, languages: list[str], *,
    user_agent: str, timeout: float = 10.0, client: httpx.Client | None = None,
) -> ResolvedTopic:
    """Map an explicit selection; never search for replacement pages.

    Selection is revalidated. Shared source/langlinks failures raise WikipediaError;
    individual target failures remain in language_mappings. Official langlink URLs
    identify editions, avoiding assumptions about exceptional Wikidata site IDs.
    """
    _configuration(user_agent, timeout)
    _text(original_query, "Original query")
    if not isinstance(selected, TopicCandidate):
        raise WikipediaError("INVALID_REQUEST", "Select a TopicCandidate explicitly.")
    if not isinstance(languages, list) or not languages:
        raise WikipediaError("INVALID_REQUEST", "Supply a nonempty list of requested languages.")
    projects = [_project(language) for language in languages]
    if len(set(languages)) != len(languages):
        raise WikipediaError("INVALID_REQUEST", "Requested languages must be unique.")
    with nullcontext(client) if client is not None else httpx.Client() as http:
        selected = validate_topic_candidate(selected, selected.source_language,
                                             user_agent=user_agent, timeout=timeout, client=http)
        if selected.status != "valid":
            raise selected.error
        qid = selected.wikidata_id
        langlinks = _langlinks(http, selected, user_agent, timeout)
        mappings = []
        for language, project in zip(languages, projects):
            mapping = LanguageMapping(language, project, "LANGUAGE_SITELINK_MISSING")
            try:
                link = langlinks.get(language)
                if link is None:
                    raise WikipediaError("LANGUAGE_SITELINK_MISSING", f"No {language} langlink for {qid}.")
                if _url_host(link["url"]) != project:
                    raise _invalid("Language link URL does not match the requested Wikipedia edition.")
                mapping.sitelink_title = link["title"]
                target = _page(http, link["title"], language, user_agent, timeout)
                for name in ("article_title", "page_id", "canonical_url", "wikidata_id",
                             "redirect_chain", "redirect_fragment", "warnings", "error", "status"):
                    setattr(mapping, name, getattr(target, name))
                if target.status == "valid" and target.wikidata_id != qid:
                    raise WikipediaError("TOPIC_MAPPING_MISMATCH", "Final page belongs to a different Wikidata item.")
            except WikipediaError as exc:
                mapping.status = exc.code
                mapping.error = exc
                mapping.warnings.append(str(exc))
            mappings.append(mapping)
    count = sum(mapping.status == "valid" for mapping in mappings)
    status = "resolved" if count == len(mappings) else "partial" if count else "unresolved"
    warnings = [] if status == "resolved" else ["Some requested languages could not be mapped; see individual results."]
    return ResolvedTopic(original_query, selected.source_language, qid, status, selected, mappings, warnings)
