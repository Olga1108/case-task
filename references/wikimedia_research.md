# Wikimedia Research

Research date: 2026-09-23. Scope: API research and proposed contracts only.
Product scope remains in [product_contract.md](../product_contract.md).

**Evidence labels:** **Fact** means supported by linked official documentation;
**Recommendation** means a proposed product choice; **Open** means not established
by the reviewed documentation. Request examples are illustrative, not live-tested
fixtures. No analytics formulas or implementation are specified here.

## 1. Executive Summary

**Recommendation:** retrieve daily observations for each selected article, retain
them for follow-up questions, and present complete calendar months. Start topic
discovery with Wikipedia search in the query's language, retain the selected
page's Wikidata Q-ID as the identity boundary, reuse that validated page directly
when its own edition is requested, and use its source-page langlinks to propose
other requested-edition targets for Q-ID validation. Keep selection evidence and
per-language failures visible.

The most consequential documented limitations are title-based traffic attribution
and ambiguous missing data: resolving a redirect does not merge its views into the
target, and a pageviews 404 does not establish that an article is missing.
See [redirect accounting](https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Traffic/Pageviews/Redirects)
and [Analytics troubleshooting](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/troubleshooting.html).

**Recommendation:** initially measure the current canonical title only, with an
explicit coverage warning. This choice needs agreement before implementation
because omitted aliases and previous titles can materially affect conclusions.

## 2. Pageviews API

### Endpoint and wire format

**Fact:** modern pageview coverage begins 2015-07-01.
[Pageviews reference](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html).

**Fact:** the relevant request is:

```text
GET https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{project}/{access}/{agent}/{article}/{granularity}/{start}/{end}
```

| Parameter | Documented values / meaning |
| --- | --- |
| `project` | Project domain, e.g. `pl.wikipedia.org` or `cs.wikipedia.org`; not a country |
| `access` | `all-access`, `desktop`, `mobile-web`, `mobile-app` |
| `agent` | `all-agents`, `user`, `spider`, `automated` |
| `article` | URL-encoded page title |
| `granularity` | `daily` or `monthly`; no per-article hourly option |
| `start`, `end` | `YYYYMMDDHH`; described as first and last day/hour to include |

Success is JSON with an `items` array. Each item contains `project`, `article`,
`access`, `agent`, `granularity`, `timestamp` (`YYYYMMDDHH`), and integer `views`.
The response project example omits `.org`; preserve the requested project for
provenance. Documented statuses are 200, 400, 404, 500; error objects can contain
`type`, `title`, `detail`, `status`, `method`, `uri`.
[Official endpoint schema](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json).

Illustrative daily request:

```text
https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/en.wikipedia.org/all-access/user/Intermittent_fasting/daily/2025010100/2025013100
```

### Dates, encoding, and absence

**Fact:** the per-article schema's wording indicates inclusion of the last day;
it does not separately explain monthly boundary rounding. The legacy endpoint
explicitly specifies an exclusive monthly end, which must not be transferred to
per-article requests. [Endpoint schema](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json).

**Recommendation:** represent product periods as inclusive ISO calendar dates in
UTC. For daily requests, serialize each boundary at `00`; validate returned dates
against the requested calendar. For monthly requests, use first-of-month bucket
boundaries only after validating the final-bucket behavior. **Open:** exact
monthly behavior for mid-month dates and equal boundaries needs a small live
contract check before implementation. No maximum per-article date span was found
in the reviewed schema; that is not a guarantee of unlimited requests.

**Recommendation:** keep human-readable Unicode titles internally; use the
canonical title returned by MediaWiki, replace spaces with underscores for the
pageview key, and UTF-8 percent-encode it once as a single path segment. Encode
embedded `/`, `?`, `#`, and `%`; do not use query-string `+` encoding for spaces,
double-encode, lowercase, or translate titles. URL encoding is required by the
[schema](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json);
space/underscore normalization and case-sensitive alias effects are explained in
[redirect accounting](https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Traffic/Pageviews/Redirects).

**Fact:** a nonexistent spelling returning HTTP 404 when visited does not produce
a pageview. This is different from the Analytics API's own 404.
[Redirect accounting](https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Traffic/Pageviews/Redirects).
The latter may mean zero matching views or records not yet loaded. Data normally
arrives after a period ends, but delays can exceed 24 hours.
[Troubleshooting](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/troubleshooting.html).

**Recommendation:** determine current article existence using MediaWiki's missing
page metadata, not the traffic response. A deleted or renamed page's current
absence does not prove it never had traffic. Keep absent buckets unknown rather
than silently filling them with zeros. Preserve explicit returned zero values.
[MediaWiki query documentation](https://www.mediawiki.org/wiki/API:Query).

### Daily retrieval versus direct monthly retrieval

The following are **product trade-offs**, not API guarantees:

| Concern | Daily retrieval, later monthly aggregation | Monthly retrieval |
| --- | --- | --- |
| Anomalies | Retains short spikes and their timing | Supports unusual-month detection; hides within-month shape |
| Monthly reports | Requires deterministic aggregation and completeness checks | Smaller, directly usable monthly series |
| Requests | A range request returns multiple days; not one request per day | Also a range request; fewer points does not inherently mean fewer requests |
| Payload | About 730 observations for two years per article | About 24 observations for two years per article |
| Follow-up | Can inspect a spike or narrower period from cached days | Daily follow-up needs another retrieval |
| Complexity | Calendar and missing-day handling required | Boundary and partial-month handling still required |

**Recommendation:** daily retrieval, monthly presentation. It preserves options
for the contract's anomaly sensitivity and follow-up requirements at modest MVP
scale. Do not define spike thresholds, aggregation formulas, or trend metrics in
this research step. Monthly retrieval remains a useful later reconciliation
check; it need not become a second routine data source.

### Other endpoints

All paths below share `https://wikimedia.org/api/rest_v1/metrics`.

| Endpoint | Documented purpose | MVP recommendation |
| --- | --- | --- |
| `/pageviews/aggregate/{project}/{access}/{agent}/{granularity}/{start}/{end}` | Project-wide traffic | Defer: the contract excludes implicit edition-traffic normalization |
| `/pageviews/top-by-country/{project}/{access}/{year}/{month}` | Approximate project traffic by country | Defer: does not provide the chosen article's geographic series |
| `/pageviews/top/{project}/{access}/{year}/{month}/{day}` | Top 1,000 pages; `all-days` permits a month | Defer: rankings cannot supply arbitrary-topic histories |
| `/legacy/pagecounts/aggregate/{project}/{access-site}/{granularity}/{start}/{end}` | Project totals including bots, January 2008–July 2016 | Exclude: incompatible coverage and semantics; no need for the default recent period |

[Official endpoint schema](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json).

### Operational contract

**Fact:** Analytics requests require an identifying User-Agent. Missing headers
may lead to blocking. Include a client name/version and a real contact URL or
email. [Analytics access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html).
**Recommendation:** configure `WikipediaInterest/0.1 (REAL_CONTACT_URL)` before
live integration; do not ship the placeholder as contact information.

**Fact:** Wikimedia's 2026 rate-limit guidance lists 200 requests/minute for
unauthenticated clients with compliant User-Agent identification and 10/minute for
unidentified clients. It recommends at most three concurrent requests, requires
respecting `Retry-After` on 429, and warns limits are changing. These are shared
infrastructure rules, not a guaranteed per-article throughput allowance.
[Current rate-limit guidance](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits).
The older Action API etiquette page's statement about no hard read speed limit
must not be interpreted as overriding that newer guidance.
[Action API etiquette](https://www.mediawiki.org/wiki/API:Etiquette).

**Recommendation:** use serial requests, batching metadata lookups where supported,
and a conservative local cap such as one request/second. Retry only idempotent
reads on connection failures, timeouts, 429 and transient 5xx, with exponential
backoff, jitter, and a finite attempt/time budget. Honor server retry delays; if a
delay exceeds the interaction budget, return a retryable failure. Do not repeatedly
retry invalid parameters, blocked access, or old-range 404s. Specific retry counts
are a future configuration decision, not a Wikimedia requirement.

**Fact:** Action API errors/warnings must also be inspected in the JSON body.
[Errors and warnings](https://www.mediawiki.org/wiki/API:Errors_and_warnings).
For background Action API requests, `maxlag=5` is recommended; lag errors can have
HTTP 200 plus `error.code=maxlag` and `Retry-After`. This parameter applies to
`api.php`, not the Analytics endpoint.
[Maxlag documentation](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter).

**Recommendation:** cache successful historical responses locally, recording the
full request, retrieval time and raw response. Do not treat history as immutable:
allow explicit refresh and retain the snapshot used for a reported result. Cache
resolution metadata separately and revalidate it more often. Avoid durable caching
of transient failures. Cache reuse follows Wikimedia's advice to avoid repeating
cacheable requests. [Action API etiquette](https://www.mediawiki.org/wiki/API:Etiquette).

## 3. Data Semantics and Limitations

**Fact:** qualifying pageviews are page-content requests answered with HTTP 200
or 304, typically HTML on the web or JSON for mobile apps. Edits and most special
pages are excluded; API traffic counts in this definition when it comes from the
mobile app. Counts represent requests, not unique people.
[Pageview definition](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html).

**Fact:** `spider` identifies traffic whose User-Agent declares bot behavior;
`automated` identifies additional traffic using heuristics.
[Agent categories](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html).
`user` is the classification remaining for user traffic, not proof of a human,
logged-in account, or distinct reader. Classification methods have changed over
time, including the automated-traffic changes deployed in 2020; residual bots and
classification errors remain possible.
[Bot detection](https://wikitech.wikimedia.org/wiki/Data_Platform/Data_Lake/Traffic/BotDetection).

**Recommendation:** use `agent=user` and `access=all-access`. Access categories
distinguish desktop, mobile web and mobile app delivery, not demographic segments.
Combining them avoids mistaking a shift in access channel for a topic decline.
Changing filters between editions or periods invalidates a like-for-like comparison.
[Access values](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json).

**Product interpretation:** attention is not commercial demand. Repeated visits,
news, search visibility, article scope, edits, title changes and unequal edition
audiences can change the signal. A Polish-language request does not establish a
reader's location in Poland. No geographic, demographic, causal, or purchasing
inference follows from these series. Apply the limitations already defined in the
product contract rather than inventing a market score.

## 4. Topic Resolution

### Official API options

**Fact — Action API search:** `GET https://{edition}/w/api.php` with
`action=query&list=search&srsearch=...&srnamespace=0&srlimit=5&format=json&formatversion=2`
searches article titles/content. Results expose titles, page IDs and snippets;
optional redirect-match fields add useful evidence. Snippets can contain markup.
[Search documentation](https://www.mediawiki.org/wiki/API:Search).

**Fact — REST search:**
`GET https://{edition}/w/rest.php/v1/search/page?q=...&limit=5` searches titles and
content; `/search/title` is title autocomplete. Results include identifiers,
titles, excerpts, descriptions and optional matched redirect titles. An empty
result array can be a successful response.
[REST search reference](https://www.mediawiki.org/wiki/API:REST_API/Reference#Search).

**Fact — Wikipedia page to entity:** use `action=query`, `titles=...`,
`redirects=1`, `prop=pageprops|info`, `inprop=url`, `format=json`,
`formatversion=2`. `pageprops.wikibase_item` supplies the Q-ID when present;
`info` supplies page identity and canonical URL metadata. Check the presence of
the `disambiguation` property, not its truthiness; it may be an empty string.
[Page properties](https://www.mediawiki.org/wiki/API:Pageprops),
[page information](https://www.mediawiki.org/wiki/API:Info),
[query behavior](https://www.mediawiki.org/wiki/API:Query).

**Fact — Wikidata discovery:** `wbsearchentities` is available for entity search;
Wikidata documents it as an Action API data-access option.
[Wikidata data access](https://www.wikidata.org/wiki/Wikidata:Data_access#MediaWiki_Action_API).
Illustrative request parameters on `https://www.wikidata.org/w/api.php`:
`action=wbsearchentities&search=intermittent%20fasting&language=en&type=item&limit=5&format=json`.
Entity search is a candidate source, not a guarantee of conceptual equivalence.

**Fact — source page to editions:** on the validated source Wikipedia edition,
`action=query&titles=CANONICAL_TITLE&prop=langlinks&llprop=url&lllimit=max`
returns interlanguage-link language codes, titles, and URLs. `lllang` filters one
language only; `llcontinue` is returned when another response is needed.
[Official langlinks help](https://www.mediawiki.org/wiki/API:Langlinks).

**Recommendation:** reuse the already validated source page directly when its own
edition is requested. For requested non-source editions, retrieve source-page
langlinks once, filter the requested languages, and validate every returned target
article independently. The target's `pageprops.wikibase_item` must equal the
already validated source Q-ID; langlinks supplies a candidate target title, not the
identity decision. Skip the langlinks request when no non-source edition is requested.

### Recommended MVP resolution strategy

The following is a **proposed technical strategy**, not final Agent Skill instructions:

1. Accept an explicit article or Q-ID as a strong starting identifier, then
   validate it. Otherwise identify the query language and search that Wikipedia
   edition. For the English phrase “intermittent fasting,” English is a search
   language even when only Polish and Czech are requested outputs.
2. Fetch a small candidate set with context, canonical metadata, disambiguation
   flags and Q-IDs. Prefer the Action API initially: it covers search and the
   required follow-up metadata without a second Wikipedia API style.
3. Select a supported concept using the user's meaning, candidate descriptions
   and snippets. Record the selected identifier and reason. Do not equate first
   search rank, exact text match, or greatest traffic with semantic certainty.
4. Reuse the validated source page for a requested source edition. If non-source
   editions are requested, retrieve the source page's language links once, then
   resolve and validate each target locally against the source Q-ID before requesting
   traffic. Return every requested language's status in its original order.
5. If Wikipedia discovery is inadequate, offer Wikidata search candidates as a
   fallback. Do not silently replace missing langlinks with independently searched
   near-matches or translated titles.

**Why Wikipedia first:** page context helps interpret everyday phrases and ensures
candidate discovery begins with articles. **Alternative:** Wikidata first is a
reasonable future default for explicit entities and multilingual aliases, but can
surface many items without relevant articles. Neither route removes ambiguity.
No embeddings, SPARQL dependency, or semantic-search infrastructure is needed.

**Responsibility boundary:** code retrieves, normalizes, validates identifiers,
checks namespaces/properties, maps langlinks, and returns evidence. The agent may
judge semantic relevance among supplied candidates and explain its choice. It must
not invent titles/Q-IDs or override a mapping mismatch. If multiple candidates
remain plausible, return `TOPIC_AMBIGUOUS` for a focused user clarification.
An explicit prior user selection can be reused; do not turn search rank into a
numerical confidence score.

## 5. Redirects and Cross-Language Mapping

**Fact:** query-level `redirects=1` follows input redirects and exposes mappings;
normalization is also reported. `prop=redirects` instead lists pages pointing to a
target and has continuation; it is not the same operation, and does not enumerate
double redirects. [Query redirect resolution](https://www.mediawiki.org/wiki/API:Query#Resolving_redirects),
[incoming redirects](https://www.mediawiki.org/wiki/API:Redirects).

**Fact:** hard redirect requests can render the target content under the requested
alias and accrue views to that alias. Current canonical-title retrieval therefore
does not include all redirect traffic.
[Traffic attribution](https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Traffic/Pageviews/Redirects).

**Inference from title-based attribution:** a move can split the history across
old/new names; the current Q-ID or page ID is not a historical traffic-merge key.
Resolving the current title does not reconstruct that history. A present-day alias
list also cannot prove which concept an alias represented throughout the period.
The per-article endpoint accepts a title, not a page ID.
[Endpoint schema](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json).

**Fact:** Wikidata sitelinks can intentionally point to redirects, including
redirects to sections; sitelinks are not guaranteed to be direct article links.
[Sitelink documentation](https://www.wikidata.org/wiki/Help:Sitelinks).

**Recommendation:** retain original and canonical titles plus redirect chains and
fragments. Accept a language mapping automatically only when the final page is a
main-namespace, non-disambiguation article whose Q-ID matches the selected entity.
Same Q-ID is strong structural evidence, not proof of identical article scope.
Flag differing coverage described in candidate context. Reject section redirects
or broader-page substitutions for automatic article-level comparison: the target's
whole-page traffic would not measure that narrower concept.

**Recommendation:** if a requested non-source language code is absent from the
source langlinks, return `LANGUAGE_SITELINK_MISSING`, not zero interest. The
validated source edition and other mapped languages may remain usable, but the
requested comparison is incomplete. If the source page lacks a Q-ID, return a
candidate-level issue instead of fabricating a cross-language match.

**MVP coverage proposal:** query the validated current title only and always expose
`title_coverage=current_canonical_only` plus an alias/history warning. Known moves
inside the requested interval should prevent an unqualified trend conclusion.
Automatic move-log reconstruction and alias aggregation are deferred; whether a
basic move check is essential to the first implementation remains a product decision.
No Polish/Czech titles or Q-ID for the example have been asserted without validation.

## 6. Proposed Data Contracts

Everything in this section is a **recommendation**, not an upstream response schema
or an implemented Python class. Plain records/dictionaries are sufficient initially.
Keep normalized records alongside raw upstream responses for reproducibility.

### PageviewRequest

| Field | Proposed meaning |
| --- | --- |
| `project` | Validated canonical project domain |
| `article_title` | Canonical Unicode title, not pre-encoded |
| `start_date`, `end_date` | Inclusive ISO dates, interpreted in UTC |
| `granularity` | `daily` initially; wire API also supports `monthly` |
| `access`, `agent` | Explicit filters; proposed defaults `all-access`, `user` |

Keep the original natural-language period and applied defaults in the calling
request context. Never silently truncate a request that precedes API coverage.

### PageviewPoint and PageviewSeries

- `PageviewPoint`: `date` (UTC bucket date), `views` (nonnegative integer). Raw wire
  timestamps remain in the stored upstream response.
- `PageviewSeries`: `request`, `points`, `missing_dates`, `status`
  (`complete`, `partial`, `no_data`, `failed`), `retrieved_at`, `source_url`,
  `title_coverage`, `warnings`, `issues`.
- `complete` means every expected bucket was received and validated; it does not
  certify complete conceptual coverage. Unknown buckets live in `missing_dates`,
  never as invented zero points. Reject duplicate dates, negative values and
  mismatched response filters. Preserve raw project spelling while normalizing
  recognized equivalent domain forms.

### TopicCandidate

`candidate_id`, `source_language`, `article_title`, `page_id`, `canonical_url`,
`wikidata_id` (nullable), `label`, `description`, `snippet`, `search_rank`,
`is_disambiguation`, `resolution_method`, `warnings`.

Rank is retrieval metadata only. Return cleaned plain-text snippets to the agent;
retain their source. Bound the candidate list, e.g. five entries, to keep ambiguity
review practical. Labels and descriptions may be missing.

### ResolvedTopic and LanguageMapping

- `ResolvedTopic`: `original_query`, `query_language`, `wikidata_id` (nullable until
  selection), `status` (`resolved`, `partial`, `ambiguous`, `unresolved`),
  `selection_method` (`explicit_user`, `agent_selected`), `selection_reason`,
  `candidates`, `language_mappings`, `resolved_at`, `warnings`.
- `LanguageMapping`: `language`, `site_id`, `project`, `status`, `sitelink_title`,
  `article_title`, `page_id`, `canonical_url`, `wikidata_id`, `redirect_chain`,
  `redirect_fragment`, `resolution_method`, `warnings`, `issues`.
- Missing mappings have null article fields and a concrete issue. Differentiate
  the selected topic Q-ID from the final page Q-ID so mismatches remain inspectable.
  For Polish/Czech, site IDs are `plwiki`/`cswiki`; validate other editions rather
  than assuming every language code has an identical host/site-ID pattern.

### Issue

`code`, `message`, `stage`, optional `language`, `retryable`, optional
`http_status`, optional `upstream_code`, optional `retry_after_seconds`.
Warnings can use the same simple record shape. No exception hierarchy is proposed.

## 7. Failure Cases

These are **proposed application states**; their names are not Wikimedia error codes.

| State | Trigger / appropriate response |
| --- | --- |
| `TOPIC_NOT_FOUND` | No usable candidates; request another name or explicit identifier |
| `TOPIC_AMBIGUOUS` | Several plausible meanings; return evidence-bearing candidates |
| `ARTICLE_NOT_FOUND` | MediaWiki explicitly reports missing canonical page; not inferred from Analytics 404 |
| `WIKIDATA_ITEM_MISSING` | Article lacks Q-ID; cannot validate automatic cross-language mapping |
| `LANGUAGE_SITELINK_MISSING` | Selected entity has no requested site link; retain partial language result |
| `LANGUAGE_UNSUPPORTED` | Unknown or unsupported edition/site mapping |
| `DISAMBIGUATION_PAGE` | Candidate is a disambiguation page; require a specific topic |
| `TOPIC_MAPPING_MISMATCH` | Final target Q-ID differs, section target is broader, or identity cannot be verified |
| `REDIRECT_UNRESOLVED` | Circular, broken, interwiki, or otherwise unresolved target |
| `INVALID_DATE_RANGE` | Malformed/reversed dates, unsupported coverage or disallowed partial period |
| `PAGEVIEWS_NO_DATA` | Analytics 404/no records; cause may be zero or unavailable data |
| `DATA_INCOMPLETE` | Expected daily buckets absent; avoid complete-month claims |
| `TITLE_HISTORY_UNVERIFIED` | Coverage warning for aliases/moves; escalate known discontinuities |
| `RATE_LIMITED` | HTTP 429 or equivalent upstream throttling; honor delay and retry budget |
| `ACCESS_BLOCKED` | Access rejection; check identification/configuration, do not retry indefinitely |
| `API_UNAVAILABLE` | Transport/server failure or persistent maxlag after bounded retry |
| `INVALID_API_RESPONSE` | Malformed body, missing required data, duplicates, invalid values or mismatched filters |

The distinction between transport success and Action API application errors is
documented in [Errors and warnings](https://www.mediawiki.org/wiki/API:Errors_and_warnings).
The no-data ambiguity is documented in
[Analytics troubleshooting](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/troubleshooting.html).

## 8. Recommended MVP Decisions

### 1. Retrieval granularity

**Decision:** daily source data, complete-month reporting.
**Reason:** retain short-spike evidence and support narrower follow-up periods.
**Alternative considered:** monthly-only retrieval.
**Why not now:** loses daily detail needed to investigate unusual months.

### 2. Access filter

**Decision:** `all-access` by default, recorded explicitly.
**Reason:** include all delivery channels in the attention signal.
**Alternative considered:** desktop or mobile-only views.
**Why not now:** channel-specific research is not the initial question.

### 3. Agent filter

**Decision:** `user` by default, described as classified user traffic.
**Reason:** reduce identified automated traffic while acknowledging residual errors.
**Alternative considered:** `all-agents`.
**Why not now:** bot activity is not the intended interest signal.

### 4. Topic resolution

**Decision:** Wikipedia Action API discovery, then source-page langlinks followed
by target-page validation against the selected Wikidata Q-ID; allow Wikidata
discovery fallback.
**Reason:** combines article context with explicit cross-language identity.
**Alternative considered:** Wikidata-first for every phrase or independent translated searches.
**Why not now:** the former may lack article context; the latter can silently mix concepts.

### 5. Redirect handling

**Decision:** resolve inputs and langlinks; initially measure only the canonical
title and show the coverage limitation. Stop unqualified interpretation of known moves.
**Reason:** transparent, bounded first implementation.
**Alternative considered:** aggregate every alias and reconstruct title histories.
**Why not now:** historical alias membership and topic scope require additional validation.

### 6. Cache strategy

**Decision:** local historical response snapshots keyed by all request fields;
explicit refresh, provenance, and a separate shorter-lived resolution cache.
**Reason:** reuse follow-up data and reproduce a result from its exact input snapshot.
**Alternative considered:** always fetch, or cache forever without refresh.
**Why not now:** the former wastes requests; the latter conceals corrections and mapping changes.

### 7. Ambiguity

**Decision:** return a small candidate list with identifiers, descriptions, snippets
and warnings; let the agent select with a reason or ask the user when uncertain.
**Reason:** semantic choice needs context, while structural validation belongs in code.
**Alternative considered:** always choose the first result or invent a confidence score.
**Why not now:** neither establishes that the chosen article matches user intent.

### 8. Missing data and partial languages

**Decision:** keep unknown data distinct from zero; preserve per-language failures.
**Reason:** avoid interpreting absence as low interest or an incomplete comparison as complete.
**Alternative considered:** zero-fill all gaps or silently drop failing languages.
**Why not now:** either can distort the product conclusion.

## 9. Open Questions

1. **Monthly wire boundaries:** verify aligned, mid-month and equal-boundary calls,
   plus daily equal-boundary inclusion. Check month-end and leap-day cases before
   writing the adapter; do not borrow legacy monthly semantics.
2. **Date span and service behavior:** no explicit maximum span was found. Confirm
   the default 24-month daily request and practical limits without load testing.
3. **Missing buckets:** what evidence is sufficient to label old absent observations
   zero? Until settled, retain unknowns. Calendar completion alone does not prove
   the latest month has fully loaded.
4. **Title coverage:** is a canonical-only warning sufficient, or should the first
   data client check moves during the selected interval? Full alias history remains
   deferred. Decide when known moves block comparisons.
5. **Resolution acceptance:** agree examples of safe agent selection versus required
   clarification, and whether single-language operation without a Q-ID is allowed.
6. **Partial success:** recommend returning valid languages but withholding any
   comparison that requires a missing language. Confirm the desired product behavior.
7. **Operational settings:** choose a real User-Agent contact, retry budget, cache
   refresh/retention periods and when resolution metadata must be revalidated.
8. **Example verification:** the actual current entity and Polish/Czech articles
   for “intermittent fasting” still need a live resolution fixture, including a
   mismatch/absent-langlink case. This document does not claim tested mappings.

No production integration, API fixture tests, analytics formulas, or final skill
workflow were implemented during this research. The official reference and its
embedded machine-readable schema were inspected; examples above are design examples.

## 10. Official Sources

Reviewed on 2026-09-23. Links also appear beside the claims they support.

1. [Wikimedia Analytics pageviews reference](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/reference/page-views.html)
2. [Official pageviews OpenAPI schema](https://wikimedia.org/api/rest_v1/metrics/pageviews/api-spec.json) — embedded by the reference page; parameter and response definitions.
3. [Analytics access policy](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/access-policy.html)
4. [Analytics troubleshooting](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/documentation/troubleshooting.html)
5. [Pageview concepts](https://doc.wikimedia.org/generated-data-platform/aqs/analytics-api/concepts/page-views.html)
6. [Redirect traffic accounting](https://wikitech.wikimedia.org/wiki/Analytics/Data_Lake/Traffic/Pageviews/Redirects)
7. [Bot detection](https://wikitech.wikimedia.org/wiki/Data_Platform/Data_Lake/Traffic/BotDetection)
8. [Current Wikimedia rate limits](https://www.mediawiki.org/wiki/Wikimedia_APIs/Rate_limits)
9. [Action API etiquette](https://www.mediawiki.org/wiki/API:Etiquette)
10. [Maxlag parameter](https://www.mediawiki.org/wiki/Manual:Maxlag_parameter)
11. [Action API errors and warnings](https://www.mediawiki.org/wiki/API:Errors_and_warnings)
12. [Action API search](https://www.mediawiki.org/wiki/API:Search)
13. [MediaWiki REST search](https://www.mediawiki.org/wiki/API:REST_API/Reference#Search)
14. [Action API query and redirect resolution](https://www.mediawiki.org/wiki/API:Query)
15. [Page properties](https://www.mediawiki.org/wiki/API:Pageprops)
16. [Page information](https://www.mediawiki.org/wiki/API:Info)
17. [Incoming redirects](https://www.mediawiki.org/wiki/API:Redirects)
18. [Wikidata data access](https://www.wikidata.org/wiki/Wikidata:Data_access)
19. [Action API language links](https://www.mediawiki.org/wiki/API:Langlinks)
20. [Wikidata sitelinks](https://www.wikidata.org/wiki/Help:Sitelinks)
