# Product Contract

## 1. Product Goal

Help B2C product teams use Wikipedia pageview data as an early signal of audience interest when deciding which topics or language markets are worth investigating further.

The skill must transform a natural-language research question into a reproducible analysis with:

- resolved Wikipedia topics/pages;
- historical pageview data;
- comparable trend metrics;
- evidence-quality checks;
- clear visualizations;
- concise decision-oriented conclusions;
- an optional shareable one-page report.

Wikipedia pageviews are treated as an attention signal, not as direct evidence of market demand, purchase intent, or product-market fit.

## 2. Target User

Primary users:

- founders of B2C products;
- product managers;
- growth or market research teams.

The user is expected to have a product hypothesis such as:

- whether a topic is gaining interest;
- which language market shows stronger signals;
- which audience should be investigated next.

The user should not need to know Wikipedia APIs, article titles, statistical methods, or data-processing details.

## 3. Jobs To Be Done

When evaluating a possible product direction, the user wants to:

1. Measure how interest in a topic has changed over time.
2. Compare that change across selected Wikipedia language editions.
3. Distinguish sustained trends from temporary traffic spikes.
4. Understand how strong or weak the evidence behind the observed trend is.
5. Identify which hypotheses deserve further validation.
6. Refine the analysis through follow-up questions without restarting the research from scratch.
7. Produce a concise result that can be shared with teammates.

## 4. Supported Questions

The MVP should support questions such as:

- Is interest in topic X growing or declining in language Y?
- Compare interest in topic X across languages A, B, and C.
- Which selected language markets show stronger growth for topic X?
- Is the observed growth sustained or mainly caused by temporary spikes?
- How reliable is the observed trend?
- Re-run the previous analysis using another period.
- Add or remove a language from an existing comparison.
- Exclude an identified anomaly and recalculate the result.
- Generate a concise shareable report from the current analysis.

The MVP does not aim to determine whether a market should be entered or whether users are willing to pay.

## 5. Inputs

The skill should accept natural-language requests and derive the following inputs:

* one topic or concept to analyze;
* one or more Wikipedia language editions;
* an analysis period;
* an optional comparison criterion;
* an optional output format.

Examples:

* topic: `intermittent fasting`
* languages: `pl`, `cs`
* period: `last 24 months`
* comparison criterion: `growth and trend stability`
* output: `chat summary`, `chart`, or `one-page PDF`

### Defaults

If the user does not specify all parameters, the skill may apply documented defaults.

For the MVP:

* default analysis period: last 24 complete months;
* default comparison dimensions:

  * attention volume;
  * growth;
  * trend consistency;
  * anomaly sensitivity;
* default output:

  * concise written summary;
  * one chart;
  * structured analysis result.

The skill should avoid unnecessary clarification questions when a safe and explicit default can be applied.

Any applied default must be visible in the result.

---

## 6. Outputs

Each completed analysis should produce a structured result that can be reused by both the agent and later reporting steps.

The MVP output should include:

### Resolved topic

* the concept requested by the user;
* the Wikipedia article selected for each language;
* the language edition;
* any ambiguity or mapping warnings.

### Analysis period

* requested or default period;
* effective start date;
* effective end date;
* data granularity.

### Metrics

At minimum:

* total or average attention volume;
* growth over the selected period;
* trend direction;
* trend consistency;
* anomaly information;
* evidence/confidence assessment.

### Interpretation

A concise explanation of:

* what changed;
* whether the observed change appears sustained;
* important differences between selected language editions;
* which hypotheses deserve further validation.

### Limitations

The result must explicitly mention relevant limitations that could affect interpretation.

### Artifacts

When requested or appropriate:

* chart image;
* structured JSON result;
* one-page shareable PDF report.

---

## 7. Definition of Wikipedia Interest

For this product, `Wikipedia interest` means observed attention to a topic as approximated by pageviews of relevant Wikipedia articles over time.

Wikipedia pageviews are treated as a proxy for information-seeking behavior.

They are not treated as direct evidence of:

* willingness to pay;
* product demand;
* product-market fit;
* market size;
* conversion potential;
* user retention;
* commercial intent.

The purpose of the signal is to support prioritization of further research, not to make a final market-entry or product-investment decision.

The skill should therefore use language such as:

* `shows stronger attention signals`;
* `shows sustained growth`;
* `deserves further validation`;
* `provides weak/medium/strong evidence of increasing interest`.

It should avoid unsupported claims such as:

* `this is the best market`;
* `users will pay`;
* `this market will perform better`;
* `the product should definitely launch here`.

---

## 8. Core Analysis Dimensions

The MVP evaluates a topic using separate analysis dimensions rather than a single combined score.

### 8.1 Attention volume

Measures how much traffic the selected topic receives within a Wikipedia language edition.

Possible representations include:

* total views;
* average monthly views;
* median monthly views.

Volume provides context but is not a direct proxy for market size.

### 8.2 Direction of change

Determines whether observed interest is:

* increasing;
* decreasing;
* approximately stable.

### 8.3 Magnitude of change

Measures how large the observed change is over the selected analysis period.

The exact calculation methodology is defined separately in `references/metrics.md`.

### 8.4 Trend consistency

Evaluates whether change is broadly sustained over time or concentrated in a small number of observations.

### 8.5 Anomaly sensitivity

Evaluates whether the conclusion materially changes when unusual traffic spikes are excluded or down-weighted.

### 8.6 Evidence quality

Summarizes how much confidence should be placed in the observed trend based on measurable properties of the data.

Evidence quality must remain separate from the product recommendation itself.

---

## 9. Evidence / Confidence

The skill should communicate how strongly the available Wikipedia data supports a trend conclusion.

For the MVP, evidence quality may be expressed using human-readable categories such as:

* high;
* medium;
* low.

The exact scoring or classification formula is intentionally not defined in the product contract and must be documented in `references/methodology.md`.

Evidence quality should consider factors such as:

* data completeness;
* amount of historical data;
* traffic volume;
* consistency of the trend;
* volatility;
* presence and influence of outliers;
* sensitivity of the conclusion to anomalous periods.

The skill must explain the reason for a confidence assessment.

Example:

`Confidence: Medium — the topic shows positive growth, but a significant share of the increase is concentrated in two high-traffic months.`

The agent must not present confidence labels without supporting evidence.

---

## 10. Cross-Language Comparison Rules

Comparisons between Wikipedia language editions must distinguish between:

### Within-language change

How interest in a topic changes over time inside one Wikipedia edition.

This is the primary basis for comparing growth trends across languages.

### Cross-language absolute traffic

Absolute pageview counts may be shown for context, but they must not be interpreted directly as equivalent market sizes.

Different Wikipedia language editions differ in:

* total traffic;
* user population;
* Wikipedia usage behavior;
* content coverage;
* article maturity;
* external search visibility.

Therefore:

* absolute traffic may be compared descriptively;
* growth rates may be compared more directly;
* conclusions about relative market opportunity must remain cautious.

The MVP should not normalize traffic by total Wikipedia-language traffic unless that normalization is explicitly implemented and documented.

---

## 11. Assumptions

The MVP operates under the following assumptions:

1. Wikipedia pageviews provide a useful but imperfect signal of public attention.
2. The resolved Wikipedia article is a reasonable representation of the user’s requested topic.
3. Historical pageview trends may help identify topics or language audiences worth investigating further.
4. Trend direction is more useful than isolated single-period values.
5. Sustained trends are generally more informative than short-lived spikes.
6. Users prefer concise, decision-oriented results over raw data dumps.
7. Deterministic code should perform calculations, while the agent should primarily handle intent interpretation and result explanation.
8. Historical data should be reusable for follow-up questions whenever possible.
9. The same methodology should produce reproducible results when run against the same underlying data and configuration.

These assumptions must be revisited if later product iterations introduce additional data sources or broader market-research use cases.

---

## 12. Limitations

The skill must make relevant limitations visible to the user.

Known MVP limitations include:

### Wikipedia is only one signal

Wikipedia traffic does not measure commercial intent, willingness to pay, conversion, retention, or competitive intensity.

### Topic resolution may be imperfect

A user concept may:

* map to multiple Wikipedia articles;
* have different scopes across language editions;
* be missing in some languages;
* have redirects or naming differences.

Ambiguous mappings must be surfaced instead of silently hidden.

### Language editions are not directly equivalent

Wikipedia usage patterns vary across languages, so absolute traffic cannot be interpreted as directly comparable market demand.

### External events may distort traffic

News events, celebrity mentions, releases, political events, scientific discoveries, or other short-term attention drivers can cause temporary spikes.

### Low-volume topics are less reliable

Very low traffic may make trend conclusions unstable.

### Historical trends do not guarantee future behavior

The skill describes observed historical signals and should not present them as forecasts.

### Article-level analysis may underrepresent broad topics

A broad concept may require multiple related Wikipedia pages to represent audience interest accurately. Multi-article topic clusters are outside the initial MVP unless explicitly added later.

---

## 13. MVP Scope

The first usable version should support an end-to-end workflow for one topic across one or more Wikipedia language editions.

The MVP includes:

* natural-language request handling through the Agent Skill;
* extraction of topic, languages and analysis period;
* resolution of the requested topic to Wikipedia articles;
* retrieval of historical Wikipedia pageview data;
* local caching of retrieved historical data where practical;
* deterministic data aggregation;
* growth and trend analysis;
* basic anomaly detection;
* evidence/confidence assessment;
* cross-language comparison;
* structured reusable analysis output;
* one clear chart;
* concise decision-oriented explanation;
* optional one-page PDF report;
* follow-up analysis using changed periods, languages or assumptions;
* automated tests for core deterministic logic;
* evaluation of the skill with a low-cost tool-capable model.

The MVP should prioritize correctness, interpretability and reproducibility over feature breadth.

---

## 14. Out of Scope

The following capabilities are explicitly outside the first MVP:

* predicting future demand;
* estimating revenue or willingness to pay;
* automatically deciding whether a company should enter a market;
* calculating product-market fit;
* sentiment analysis;
* user demographic inference;
* competitor analysis;
* App Store or Google Play analysis;
* Google Trends integration;
* SEO search-volume integration;
* social-media analysis;
* Reddit, YouTube or TikTok analysis;
* paid advertising data;
* automatic market-size estimation;
* large-scale analysis of hundreds or thousands of topics;
* complex machine-learning forecasting;
* advanced causal analysis;
* semantic clustering of large sets of Wikipedia pages;
* a standalone web application or dashboard.

These may be considered in future iterations if they improve the product decision workflow.

---

## 15. Success Criteria

The MVP is successful if an AI agent can reliably use the skill to answer representative product-research questions without requiring the model to perform numerical analysis itself.

### Functional success criteria

The skill should be able to:

1. Resolve a user topic to relevant Wikipedia articles in selected language editions.
2. Retrieve pageview data for the requested period.
3. Calculate the same deterministic metrics consistently.
4. Detect and surface important data-quality or anomaly issues.
5. Compare trends across multiple selected languages.
6. Produce a concise explanation grounded in calculated results.
7. Generate a readable chart.
8. Generate a one-page shareable report when requested.
9. Reuse previous data or analysis where possible for related follow-up requests.

### Product-quality criteria

The result should:

* answer the user’s actual decision question;
* clearly distinguish data from interpretation;
* expose assumptions and limitations;
* avoid overstating what Wikipedia data proves;
* explain the strength of the available evidence;
* suggest a reasonable next validation step when appropriate.

### Agent-quality criteria

When tested on a low-cost tool-capable model, the skill should:

* select the correct workflow;
* invoke deterministic code rather than calculate metrics manually;
* pass correct parameters to tools;
* notice warnings returned by the analysis;
* preserve important assumptions;
* avoid unsupported conclusions;
* handle representative follow-up requests.

### Engineering-quality criteria

The implementation should:

* be reproducible from the repository;
* have documented dependencies;
* contain no compiled artifacts;
* keep core calculations testable and deterministic;
* include automated tests for important analytical logic;
* fail clearly when data or topic resolution is insufficient;
* keep the Agent Skill instructions concise enough for efficient use by smaller models.
