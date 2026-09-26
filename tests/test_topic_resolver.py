"""Synthetic Action API fixtures; all HTTP is intercepted by MockTransport."""

import httpx
import pytest

from wikipedia_interest import topic_resolver
from wikipedia_interest.models import TopicCandidate, WikipediaError
from wikipedia_interest.topic_resolver import (
    map_topic_languages, search_topic_candidates, validate_topic_candidate,
)

UA = "WikipediaInterestTests/0.1 (https://example.org/contact)"


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(topic_resolver.time, "sleep", lambda _: None)


def page(title="Fasting", qid="Q123", language="en", **changes):
    record = dict(pageid=10, ns=0, title=title,
                  canonicalurl=f"https://{language}.wikipedia.org/wiki/{title.replace(' ', '_')}",
                  pageprops={"wikibase_item": qid} if qid else {})
    return {"query": {"pages": [record | changes]}}


def langlinks(languages=("pl", "cs"), **changes):
    record = {"pageid": 10, "ns": 0, "title": "Fasting", "langlinks": [
        {"lang": language, "title": f"Fasting {language}",
         "url": f"https://{language}.wikipedia.org/wiki/Fasting_{language}"}
        for language in languages
    ]}
    return {"batchcomplete": True, "query": {"pages": [record | changes]}}


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


def mapping(responses, languages=("pl", "cs"), candidate=None):
    calls = []
    with httpx.Client(transport=transport(responses, calls)) as client:
        result = map_topic_languages("intermittent fasting", candidate or selected(), list(languages),
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
        page("B", qid=None), *[httpx.Response(503) for _ in range(3)]]
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
    result, calls = mapping([page(), langlinks(), page("Fasting pl", language="pl"), page("Fasting cs", language="cs")])
    assert result.status == "resolved"
    assert [m.wikidata_id for m in result.language_mappings] == ["Q123", "Q123"]
    assert all(m.status == "valid" for m in result.language_mappings)
    assert [m.language for m in result.language_mappings] == ["pl", "cs"]
    assert calls[1].url.host == "en.wikipedia.org"
    assert calls[1].url.params["prop"] == "langlinks"
    assert calls[1].url.params["titles"] == "Fasting"
    assert calls[1].url.params["llprop"] == "url"
    assert calls[1].url.params["lllimit"] == "max"
    assert all(call.url.host != "www.wikidata.org" for call in calls)


def test_source_only_reuses_redirected_canonical_page_without_langlinks():
    source = TopicCandidate("en", "BTC", wikidata_id="Q131723", status="valid")
    validated = page("Bitcoin", "Q131723", "en")
    validated["query"]["redirects"] = [{"from": "BTC", "to": "Bitcoin"}]

    result, calls = mapping([validated], ("en",), source)

    assert result.status == "resolved"
    mapped, = result.language_mappings
    assert (mapped.language, mapped.project, mapped.status) == (
        "en", "en.wikipedia.org", "valid",
    )
    assert mapped.article_title == "Bitcoin"
    assert mapped.wikidata_id == result.wikidata_id == "Q131723"
    assert mapped.redirect_chain == ["BTC", "Bitcoin"]
    assert len(calls) == 1
    assert calls[0].url.params["titles"] == "BTC"
    assert calls[0].url.params["prop"] == "pageprops|info"


@pytest.mark.parametrize("languages", [("en", "es"), ("es", "en")])
def test_bitcoin_source_reuse_and_target_langlink_preserve_requested_order(languages):
    source = TopicCandidate("en", "Bitcoin", wikidata_id="Q131723", status="valid")
    links = langlinks(("es",), title="Bitcoin")
    link = links["query"]["pages"][0]["langlinks"][0]
    link.update(title="Bitcoin", url="https://es.wikipedia.org/wiki/Bitcoin")

    result, calls = mapping([
        page("Bitcoin", "Q131723", "en"), links,
        page("Bitcoin", "Q131723", "es"),
    ], languages, source)

    assert result.status == "resolved"
    assert [item.language for item in result.language_mappings] == list(languages)
    mapped = {item.language: item for item in result.language_mappings}
    assert mapped["en"].article_title == "Bitcoin"
    assert mapped["en"].wikidata_id == "Q131723"
    assert mapped["es"].article_title == "Bitcoin"
    assert mapped["es"].wikidata_id == "Q131723"
    assert [(call.url.host, call.url.params.get("prop")) for call in calls] == [
        ("en.wikipedia.org", "pageprops|info"),
        ("en.wikipedia.org", "langlinks"),
        ("es.wikipedia.org", "pageprops|info"),
    ]
    assert sum(call.url.params.get("prop") == "langlinks" for call in calls) == 1
    assert all("srsearch" not in call.url.params for call in calls)
    assert all(call.url.host != "www.wikidata.org" for call in calls)


def test_source_stays_valid_when_target_langlink_is_missing():
    source = TopicCandidate("en", "Bitcoin", wikidata_id="Q131723", status="valid")
    result, calls = mapping([
        page("Bitcoin", "Q131723", "en"), langlinks((), title="Bitcoin"),
    ], ("en", "xx"), source)

    assert result.status == "partial"
    english, missing = result.language_mappings
    assert english.status == "valid"
    assert english.article_title == "Bitcoin"
    assert english.wikidata_id == "Q131723"
    assert missing.status == "LANGUAGE_SITELINK_MISSING"
    assert missing.error.code == "LANGUAGE_SITELINK_MISSING"
    assert len(calls) == 2


def test_source_stays_valid_when_target_qid_mismatches():
    source = TopicCandidate("en", "Bitcoin", wikidata_id="Q131723", status="valid")
    links = langlinks(("es",), title="Bitcoin")
    link = links["query"]["pages"][0]["langlinks"][0]
    link.update(title="Bitcoin", url="https://es.wikipedia.org/wiki/Bitcoin")
    result, _ = mapping([
        page("Bitcoin", "Q131723", "en"), links,
        page("Bitcoin", "Q999", "es"),
    ], ("en", "es"), source)

    assert result.status == "partial"
    english, spanish = result.language_mappings
    assert english.status == "valid"
    assert spanish.status == "TOPIC_MAPPING_MISMATCH"
    assert spanish.error.code == "TOPIC_MAPPING_MISMATCH"


def test_czech_and_ukrainian_langlinks_validate_localized_titles_in_requested_order():
    payload = langlinks(("cs", "uk"))
    cs, uk = payload["query"]["pages"][0]["langlinks"]
    cs.update(title="Přerušovaný půst", url="https://cs.wikipedia.org/wiki/Přerušovaný_půst")
    uk.update(title="Інтервальне голодування",
              url="https://uk.wikipedia.org/wiki/Інтервальне_голодування")
    result, calls = mapping([
        page(), payload,
        page("Інтервальне голодування", language="uk"),
        page("Přerušovaný půst", language="cs"),
    ], ("uk", "cs"))
    assert result.status == "resolved"
    assert [item.language for item in result.language_mappings] == ["uk", "cs"]
    assert [item.article_title for item in result.language_mappings] == [
        "Інтервальне голодування", "Přerušovaný půst",
    ]
    assert [call.url.params.get("titles") for call in calls[2:]] == [
        "Інтервальне голодування", "Přerušovaný půst",
    ]
    assert all("srsearch" not in call.url.params for call in calls)
    assert all(call.url.host != "www.wikidata.org" for call in calls)


def test_langlinks_continuation_is_followed_before_requested_order_mapping():
    first = langlinks(("cs",))
    first.pop("batchcomplete")
    first["continue"] = {"continue": "||", "llcontinue": "10|cs"}
    second = langlinks(("uk",))
    result, calls = mapping([
        page(), first, second,
        page("Fasting uk", language="uk"), page("Fasting cs", language="cs"),
    ], ("uk", "cs"))
    assert result.status == "resolved"
    assert [item.language for item in result.language_mappings] == ["uk", "cs"]
    assert calls[2].url.params["continue"] == "||"
    assert calls[2].url.params["llcontinue"] == "10|cs"


def test_intermittent_fasting_czech_present_polish_missing_no_replacement_search():
    # Synthetic regression scenario, not an assertion about current live sitelinks.
    result, calls = mapping([page(), langlinks(("cs",)), page("Fasting cs", language="cs")])
    assert result.original_query == "intermittent fasting"
    assert result.status == "partial"
    polish, czech = result.language_mappings
    assert polish.status == "LANGUAGE_SITELINK_MISSING"
    assert polish.article_title is None and polish.wikidata_id is None
    assert czech.status == "valid"
    assert all(call.url.host != "pl.wikipedia.org" for call in calls)
    assert all("srsearch" not in call.url.params for call in calls)


def test_langlinks_maxlag_then_success_retries_same_request():
    maxlag = httpx.Response(
        200, json={"error": {"code": "maxlag", "info": "Waiting for wdqs1016"}},
        headers={"Retry-After": "0"},
    )
    result, calls = mapping([
        page(), maxlag, langlinks(("cs",)), page("Fasting cs", language="cs"),
    ], ("cs",))
    assert result.status == "resolved"
    first, second = calls[1:3]
    assert first.url == second.url
    assert first.url.host == "en.wikipedia.org"
    assert first.url.params["action"] == "query"
    assert first.url.params["titles"] == "Fasting"
    assert first.url.params["prop"] == "langlinks"
    assert first.url.params["maxlag"] == "5"
    assert all("srsearch" not in call.url.params for call in calls)


def test_langlinks_503_then_success():
    result, calls = mapping([
        page(), httpx.Response(503), langlinks(("cs",)), page("Fasting cs", language="cs"),
    ], ("cs",))
    assert result.status == "resolved"
    assert calls[1].url == calls[2].url


def test_langlinks_429_respects_retry_after(monkeypatch):
    waits = []
    monkeypatch.setattr(topic_resolver.time, "sleep", waits.append)
    result, _ = mapping([
        page(), httpx.Response(429, headers={"Retry-After": "2"}),
        langlinks(("cs",)), page("Fasting cs", language="cs"),
    ], ("cs",))
    assert result.status == "resolved"
    assert waits == [2.0]


def test_langlinks_retry_budget_exhausted_preserves_error():
    maxlag = lambda: httpx.Response(
        200, json={"error": {"code": "maxlag", "info": "busy"}},
        headers={"Retry-After": "0"},
    )
    calls = []
    responses = [page(), maxlag(), maxlag(), maxlag()]
    with httpx.Client(transport=transport(responses, calls)) as client:
        with pytest.raises(WikipediaError) as error:
            map_topic_languages("fasting", selected(), ["cs"], user_agent=UA, client=client)
    assert error.value.code == "API_UNAVAILABLE"
    assert error.value.retry_after == "0"
    assert len(calls) == 4
    assert calls[1].url == calls[2].url == calls[3].url


def test_semantic_action_error_is_not_retried():
    response = {"error": {"code": "badvalue", "info": "invalid parameter"}}
    calls = []
    with httpx.Client(transport=transport([response], calls)) as client:
        with pytest.raises(WikipediaError) as error:
            search_topic_candidates("fasting", "en", user_agent=UA, client=client)
    assert error.value.code == "INVALID_REQUEST"
    assert len(calls) == 1


def test_all_languages_missing():
    result, _ = mapping([page(), langlinks(())])
    assert result.status == "unresolved"
    assert len(result.language_mappings) == 2


@pytest.mark.parametrize("target,code", [
    (page("Fasting pl", "Q999", "pl"), "TOPIC_MAPPING_MISMATCH"),
    (page("Fasting pl", language="pl", ns=1), "NON_MAIN_NAMESPACE"),
    (page("Fasting pl", language="pl", pageprops={"disambiguation": "", "wikibase_item": "Q123"}), "DISAMBIGUATION_PAGE"),
    (page("Fasting pl", qid=None, language="pl"), "WIKIDATA_ITEM_MISSING"),
    (httpx.Response(429, headers={"Retry-After": "60"}), "RATE_LIMITED"),
    ([httpx.Response(503) for _ in range(3)], "API_UNAVAILABLE"),
    ({"query": {}}, "INVALID_API_RESPONSE"),
])
def test_target_failure_does_not_discard_other_language(target, code):
    targets = target if isinstance(target, list) else [target]
    result, _ = mapping([page(), langlinks(), *targets, page("Fasting cs", language="cs")])
    assert result.status == "partial"
    assert result.language_mappings[0].status == code
    assert result.language_mappings[0].error.code == code
    assert result.language_mappings[1].status == "valid"
    if code == "RATE_LIMITED":
        assert result.language_mappings[0].error.retry_after == "60"


def test_target_redirect_with_matching_qid():
    target = page("Canonical", language="cs")
    target["query"]["redirects"] = [{"from": "Fasting cs", "to": "Canonical"}]
    result, _ = mapping([page(), langlinks(("cs",)), target], ("cs",))
    assert result.status == "resolved"
    mapped = result.language_mappings[0]
    assert mapped.sitelink_title == "Fasting cs"
    assert mapped.article_title == "Canonical"
    assert mapped.redirect_chain == ["Fasting cs", "Canonical"]


def test_langlink_uses_official_url_host():
    result, _ = mapping([page(), langlinks(("cs",)), page("Fasting cs", language="cs")], ("cs",))
    assert result.status == "resolved"


@pytest.mark.parametrize("response,code", [
    (httpx.Response(429, headers={"Retry-After": "120"}), "RATE_LIMITED"),
    (httpx.Response(403), "ACCESS_BLOCKED"),
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
    assert len(calls) == 1
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


def test_malformed_langlink_url_is_a_domain_failure():
    payload = langlinks(("cs",))
    payload["query"]["pages"][0]["langlinks"][0]["url"] = "https://[broken"
    result, _ = mapping([page(), payload], ("cs",))
    assert result.status == "unresolved"
    assert result.language_mappings[0].status == "INVALID_API_RESPONSE"


@pytest.mark.parametrize("payload", [
    {}, {"query": {"pages": []}}, langlinks((), pageid=11),
    langlinks((), title="Other"), langlinks((), langlinks={}),
])
def test_invalid_shared_langlinks_response(payload):
    with pytest.raises(WikipediaError) as error:
        mapping([page(), payload])
    assert error.value.code == "INVALID_API_RESPONSE"


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
