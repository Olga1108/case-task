"""Synthetic Action API fixtures; all HTTP is intercepted by MockTransport."""

import httpx
import pytest

from wikipedia_interest.models import TopicCandidate, WikipediaError
from wikipedia_interest.topic_resolver import (
    map_topic_languages, search_topic_candidates, validate_topic_candidate,
)

UA = "WikipediaInterestTests/0.1 (https://example.org/contact)"


def page(title="Fasting", qid="Q123", language="en", **changes):
    record = dict(pageid=10, ns=0, title=title,
                  canonicalurl=f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                  pageprops={"wikibase_item": qid} if qid else {})
    return {"query": {"pages": [record | changes]}}


def entity(languages=("pl", "cs")):
    return {"entities": {"Q123": {"id": "Q123", "sitelinks": {
        f"{language}wiki": {"site": f"{language}wiki", "title": f"Fasting {language}",
                           "url": f"https://{language}.wikipedia.org/wiki/Fasting_{language}"}
        for language in languages
    }}}}


def selected():
    return TopicCandidate("en", "Fasting", wikidata_id="Q123", status="valid")


def transport(responses, calls):
    def handler(request):
        calls.append(request)
        assert request.headers["User-Agent"] == UA
        assert request.url.path == "/w/api.php"
        assert request.url.params["formatversion"] == "2"
        assert request.url.params["maxlag"] == "5"
        assert request.extensions["timeout"]["read"] == 10.0
        assert responses, f"Unexpected extra request: {request.url}"
        value = responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, httpx.Response) else httpx.Response(200, json=value)
    return httpx.MockTransport(handler)


def validate(payload, title="Fasting"):
    with httpx.Client(transport=transport([payload], [])) as client:
        return validate_topic_candidate(title, "en", user_agent=UA, client=client)


def mapping(responses, languages=("pl", "cs")):
    calls = []
    with httpx.Client(transport=transport(responses, calls)) as client:
        result = map_topic_languages("intermittent fasting", selected(), list(languages),
                                     user_agent=UA, client=client)
        assert not client.is_closed
    assert not responses
    return result, calls


def test_search_is_bounded_ranked_enriched_and_not_selected():
    hits = [{"title": f"Topic {i}", "pageid": i + 1, "ns": 0,
             "snippet": '<span class="searchmatch">Fasting</span> &amp; health'} for i in range(7)]
    responses = [{"query": {"search": hits}}] + [page(f"Topic {i}") for i in range(5)]
    calls = []
    with httpx.Client(transport=transport(responses, calls)) as client:
        candidates = search_topic_candidates("fasting", "en", user_agent=UA, client=client)
    assert len(candidates) == 5
    assert [c.search_rank for c in candidates] == [1, 2, 3, 4, 5]
    assert [c.search_page_id for c in candidates] == [1, 2, 3, 4, 5]
    assert all(c.snippet == "Fasting & health" for c in candidates)
    assert all(c.wikidata_id == "Q123" and c.page_id == 10 and c.status == "valid" for c in candidates)
    assert candidates[0].canonical_url == "https://en.wikipedia.org/wiki/Topic_0"
    assert calls[0].url.params["srlimit"] == "5"
    assert calls[0].url.params["srnamespace"] == "0"
    assert len(calls) == 6


def test_empty_search():
    calls = []
    with httpx.Client(transport=transport([{"query": {"search": []}}], calls)) as client:
        assert search_topic_candidates("no results", "en", user_agent=UA, client=client) == []
    assert len(calls) == 1


def test_search_retains_disambiguation_missing_identity_and_enrichment_failure():
    responses = [{"query": {"search": [
        {"title": title, "pageid": i, "ns": 0} for i, title in enumerate(["A", "B", "C"], 1)
    ]}}, page("A", pageprops={"wikibase_item": "Q123", "disambiguation": ""}),
        page("B", qid=None), httpx.Response(503)]
    with httpx.Client(transport=transport(responses, [])) as client:
        candidates = search_topic_candidates("ambiguous", "en", user_agent=UA, client=client)
    assert [c.status for c in candidates] == ["DISAMBIGUATION_PAGE", "WIKIDATA_ITEM_MISSING", "API_UNAVAILABLE"]
    assert candidates[0].is_disambiguation
    assert candidates[1].wikidata_id is None
    assert candidates[2].search_page_id == 3
    assert candidates[2].input_title == "C"
    assert candidates[2].error.http_status == 503


def test_canonical_page():
    candidate = validate(page())
    assert candidate.status == "valid"
    assert candidate.wikidata_id == "Q123"
    assert candidate.article_title == "Fasting"


def test_redirect_and_normalization_preserved():
    payload = page()
    payload["query"].update(normalized=[{"from": "old_title", "to": "Old title"}],
                            redirects=[{"from": "Old title", "to": "Fasting"}])
    candidate = validate(payload, "old_title")
    assert candidate.input_title == "old_title"
    assert candidate.article_title == "Fasting"
    assert candidate.redirect_chain == ["Old title", "Fasting"]
    assert candidate.status == "valid"


@pytest.mark.parametrize("payload,code", [
    ({"query": {"pages": [{"title": "Fasting", "missing": True, "ns": 0}]}}, "ARTICLE_NOT_FOUND"),
    (page(ns=1), "NON_MAIN_NAMESPACE"),
    (page(pageprops={"disambiguation": "", "wikibase_item": "Q123"}), "DISAMBIGUATION_PAGE"),
    (page(qid=None), "WIKIDATA_ITEM_MISSING"),
    (page(redirect=True), "REDIRECT_UNRESOLVED"),
])
def test_semantic_validation_states(payload, code):
    candidate = validate(payload)
    assert candidate.status == code
    assert candidate.error.code == code
    assert candidate.warnings


def test_section_redirect_is_not_a_whole_topic():
    payload = page()
    payload["query"]["redirects"] = [{"from": "Narrow topic", "to": "Fasting", "tofragment": "Section"}]
    candidate = validate(payload, "Narrow topic")
    assert candidate.status == "TOPIC_MAPPING_MISMATCH"
    assert candidate.redirect_fragment == "Section"


def test_two_languages_map_same_identity():
    result, calls = mapping([page(), entity(), page("Fasting pl", language="pl"), page("Fasting cs", language="cs")])
    assert result.status == "resolved"
    assert [m.wikidata_id for m in result.language_mappings] == ["Q123", "Q123"]
    assert all(m.status == "valid" for m in result.language_mappings)
    assert calls[1].url.host == "www.wikidata.org"
    assert calls[1].url.params["props"] == "sitelinks/urls"


def test_intermittent_fasting_czech_present_polish_missing_no_replacement_search():
    # Synthetic regression scenario, not an assertion about current live sitelinks.
    result, calls = mapping([page(), entity(("cs",)), page("Fasting cs", language="cs")])
    assert result.original_query == "intermittent fasting"
    assert result.status == "partial"
    polish, czech = result.language_mappings
    assert polish.status == "LANGUAGE_SITELINK_MISSING"
    assert polish.article_title is None and polish.wikidata_id is None
    assert czech.status == "valid"
    assert all(call.url.host != "pl.wikipedia.org" for call in calls)
    assert all("srsearch" not in call.url.params for call in calls)


def test_all_languages_missing():
    result, _ = mapping([page(), entity(())])
    assert result.status == "unresolved"
    assert len(result.language_mappings) == 2


@pytest.mark.parametrize("target,code", [
    (page("Fasting pl", "Q999", "pl"), "TOPIC_MAPPING_MISMATCH"),
    (page("Fasting pl", language="pl", ns=1), "NON_MAIN_NAMESPACE"),
    (page("Fasting pl", language="pl", pageprops={"disambiguation": "", "wikibase_item": "Q123"}), "DISAMBIGUATION_PAGE"),
    (page("Fasting pl", qid=None, language="pl"), "WIKIDATA_ITEM_MISSING"),
    (httpx.Response(429, headers={"Retry-After": "60"}), "RATE_LIMITED"),
    (httpx.Response(503), "API_UNAVAILABLE"),
    ({"query": {}}, "INVALID_API_RESPONSE"),
])
def test_target_failure_does_not_discard_other_language(target, code):
    result, _ = mapping([page(), entity(), target, page("Fasting cs", language="cs")])
    assert result.status == "partial"
    assert result.language_mappings[0].status == code
    assert result.language_mappings[0].error.code == code
    assert result.language_mappings[1].status == "valid"
    if code == "RATE_LIMITED":
        assert result.language_mappings[0].error.retry_after == "60"


def test_target_redirect_with_matching_qid():
    target = page("Canonical", language="cs")
    target["query"]["redirects"] = [{"from": "Fasting cs", "to": "Canonical"}]
    result, _ = mapping([page(), entity(("cs",)), target], ("cs",))
    assert result.status == "resolved"
    mapped = result.language_mappings[0]
    assert mapped.sitelink_title == "Fasting cs"
    assert mapped.article_title == "Canonical"
    assert mapped.redirect_chain == ["Fasting cs", "Canonical"]


def test_sitelink_uses_official_url_not_guessed_site_id():
    payload = entity(("cs",))
    link = payload["entities"]["Q123"]["sitelinks"].pop("cswiki")
    payload["entities"]["Q123"]["sitelinks"]["exceptional_site_id"] = link
    result, _ = mapping([page(), payload, page("Fasting cs", language="cs")], ("cs",))
    assert result.status == "resolved"


@pytest.mark.parametrize("response,code", [
    (httpx.Response(429, headers={"Retry-After": "120"}), "RATE_LIMITED"),
    (httpx.Response(500), "API_UNAVAILABLE"), (httpx.Response(403), "ACCESS_BLOCKED"),
    (httpx.ConnectError("offline"), "API_UNAVAILABLE"),
    (httpx.ReadTimeout("timeout"), "API_UNAVAILABLE"),
    (httpx.Response(200, json={"error": {"code": "maxlag", "info": "busy"}}, headers={"Retry-After": "120"}), "API_UNAVAILABLE"),
    ({"error": {"code": "ratelimited"}}, "RATE_LIMITED"),
    ({"error": {"code": "readapidenied"}}, "ACCESS_BLOCKED"),
    (httpx.Response(200, content=b"not json"), "INVALID_API_RESPONSE"),
    ([], "INVALID_API_RESPONSE"), ({"error": "bad"}, "INVALID_API_RESPONSE"),
    ({"query": {}}, "INVALID_API_RESPONSE"),
])
def test_http_and_api_errors(response, code):
    calls = []
    with httpx.Client(transport=transport([response], calls)) as client:
        with pytest.raises(WikipediaError) as error:
            search_topic_candidates("fasting", "en", user_agent=UA, client=client)
    assert error.value.code == code
    assert len(calls) == 1  # no retries
    if isinstance(response, httpx.Response) and "Retry-After" in response.headers:
        assert error.value.retry_after == "120"


@pytest.mark.parametrize("payload", [
    {"query": {"pages": []}}, {"query": {"pages": [{}]}},
    page(pageid=True), page(ns="0"), page(pageprops=[]),
    page(qid="wrong"), page("Unrelated"), page(canonicalurl="https://example.org/"),
    page(canonicalurl="https://[broken"),
])
def test_malformed_page_metadata(payload):
    with pytest.raises(WikipediaError) as error:
        validate(payload)
    assert error.value.code == "INVALID_API_RESPONSE"


def test_source_identity_change_stops_mapping():
    with httpx.Client(transport=transport([page(qid="Q999")], [])) as client:
        with pytest.raises(WikipediaError) as error:
            map_topic_languages("fasting", selected(), ["cs"], user_agent=UA, client=client)
    assert error.value.code == "TOPIC_MAPPING_MISMATCH"


def test_malformed_sitelink_url_is_a_domain_failure():
    payload = entity(("cs",))
    payload["entities"]["Q123"]["sitelinks"]["cswiki"]["url"] = "https://[broken"
    result, _ = mapping([page(), payload], ("cs",))
    assert result.status == "unresolved"
    assert result.language_mappings[0].status == "INVALID_API_RESPONSE"


@pytest.mark.parametrize("payload,code", [
    ({}, "INVALID_API_RESPONSE"),
    ({"entities": {"Q123": {"id": "Q123", "missing": ""}}}, "WIKIDATA_ITEM_MISSING"),
    ({"entities": {"Q123": {"id": "Q999"}}}, "TOPIC_MAPPING_MISMATCH"),
    ({"entities": {"Q123": {"id": "Q123", "sitelinks": []}}}, "INVALID_API_RESPONSE"),
])
def test_invalid_shared_entity(payload, code):
    with pytest.raises(WikipediaError) as error:
        mapping([page(), payload])
    assert error.value.code == code


@pytest.mark.parametrize("options", [
    {"limit": 0}, {"limit": 6}, {"user_agent": ""}, {"user_agent": "bad\nheader"},
    {"timeout": float("inf")}, {"timeout": 0}, {"query_language": "en/evil"}, {"query": ""},
])
def test_invalid_inputs_do_not_send_http(options):
    def fail(request):
        pytest.fail("Invalid input must not send HTTP")
    with httpx.Client(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(WikipediaError) as error:
            search_topic_candidates(**(dict(query="fasting", query_language="en", user_agent=UA, client=client) | options))
    assert error.value.code == "INVALID_REQUEST"
