# Bitcoin Wikipedia Attention Analysis
## English and Spanish Editions | Sept 2024 – Aug 2026

### Executive Summary
Wikipedia evidence shows **declining information-seeking attention for Bitcoin in the Spanish edition over the last 24 months**, with both recent year-over-year trends and long-range patterns confirming negative direction. English edition data is unavailable due to a Wikidata sitelink issue.

---

## Measured Evidence by Edition

### Spanish Edition (es.wikipedia.org)
**Status:** Complete data across 24 months (Sept 2024 – Aug 2026)

#### Recent Growth (Primary Signal)
- **Latest 3-month YoY:** –60.7% (June–Aug 2026 vs. June–Aug 2025)
- **Calendar-aligned YoY (supporting):** 
  - March: –65.7%
  - April: –53.8%
  - May: –58.5%
  - June: –43.6%
  - July: –72.0%
  - August: –62.9%

#### Long-Range Trend
- **Normalized Theil–Sen slope:** –0.058 (robust estimate: 5.8% decline per month, relative to mean)
- **Normalized OLS slope:** –0.070 (supporting estimate)
- **Raw slope:** –940 monthly views per calendar month (absolute decline)

#### Direction Assessment
**Negative.** Recent YoY and robust long-range trend are both negative. Sensitivity analysis (excluding anomalies) yields consistent slopes (–0.057 before, –0.058 after MAD filter), reinforcing the downward signal.

#### Temporal Pattern
- **Peak:** November 2024 (~37,000 monthly pageviews)
- **Subsequent trajectory:** Sharp decline through early 2025, then stabilized at lower plateau (5,000–12,000 views/month by mid-2026)
- **Month-of-year seasonality:** Higher attention in winter months (Jan–Feb, Nov–Dec); lower in summer (June–Aug). Descriptive only; no causal explanation inferred.

#### Data Quality
- **Coverage:** 730 complete daily observations; no missing or zero-value days
- **Anomalies:** 43 flagged by IQR, 20 by MAD (robust median absolute deviation)
- **Largest spikes:** December 5, 2024 (3,760 views); November peaks
- **Completeness:** All 24 months fully observed; no imputation needed

---

### English Edition (en.wikipedia.org)
**Status:** Unavailable – Wikidata sitelink missing for Q131723

The English Wikipedia article "Bitcoin" exists and is widely referenced, but the current Wikidata/API mapping does not report a valid sitelink for Q131723 → en.wikipedia.org. This appears to be a transient API issue rather than a missing article. Comparison across both editions is therefore incomplete.

---

## Interpretation for Early B2C Fintech Hypothesis

### What the Evidence Does NOT Support

1. **Growing market interest or adoption signals** – Spanish Wikipedia attention is declining sharply, contradicting a narrative of rising fintech adoption in Spanish-speaking markets.

2. **Sustained consumer research activity** – The 60%+ YoY decline in pageviews suggests fewer people seeking Bitcoin information via Wikipedia, not increased engagement.

3. **Seasonal consumer behavior opportunity** – Winter peaks are observed but remain below 2025 baseline; month-of-year patterns are descriptive, not causal.

4. **Market maturity or saturation** – Wikipedia pageviews cannot distinguish between saturation (mature market, stable adoption) and waning novelty (declining interest).

---

### What the Evidence Supports for Further Validation

1. **Declining information-seeking in Spanish-language markets** – Measurable, sustained contraction in Wikipedia attention warrants investigation into:
   - Whether Spanish-language fintech users have shifted to other information sources (specialized sites, social media, YouTube)
   - Whether cyclical crypto market conditions (bull/bear cycles) drive attention volatility
   - Whether cryptocurrency regulation changes in Latin America or Spain affect search behavior

2. **Earlier spike (Nov 2024) may reflect external events** – The peak coincides with potential Bitcoin price movements or media cycles; external validation (price data, regulatory news, news volume) would clarify whether attention spikes are event-driven or signal underlying demand.

3. **Sustained low baseline suggests information supply may have shifted** – If Wikipedia was a primary entry point for fintech research and users have moved elsewhere, product validation should focus on:
   - Where Spanish-speaking consumers now seek fintech education
   - Which fintech pain points remain underserved
   - Whether B2C demand exists independent of Wikipedia interest trends

---

## Limitations

- **Single language edition:** English data unavailable; cannot compare adoption or interest across English-speaking vs. Spanish-speaking markets.
- **Wikipedia is not market demand:** Low or declining pageviews do not imply lack of willingness to pay, product-market fit, or total addressable market. They reflect information-seeking behavior only.
- **No causality:** Attention changes do not reveal why users are visiting (or not visiting). Price movement, regulation, media coverage, or saturation could all drive the observed decline.
- **Canonical-title measurement:** Chart shows traffic to the primary "Bitcoin" article only; redirects, disambiguations, and historical title variants are not merged.
- **No competitive context:** Attention to Bitcoin alone does not reveal shifts to other cryptocurrencies or fintech products.

---

## Recommended Next Validation Steps

1. **Retrieve external signals:**
   - Bitcoin price and volatility (Sept 2024 – Aug 2026)
   - Regulatory announcements affecting Spain, Mexico, or Latin America
   - News article volume (Google Trends or news aggregator data) for Bitcoin in Spanish

2. **Extend language coverage:**
   - Investigate why English sitelink is missing; retry mapping if issue resolves
   - Add Portuguese (Brazil, Portugal) and Italian to compare across additional major European/Latin American markets

3. **Conduct user research in target markets:**
   - Where do Spanish-speaking prospective fintech users currently research Bitcoin and fintech products?
   - What are the top 3 barriers to adoption for a B2C fintech product in these markets?
   - Do users perceive Wikipedia as a credible vs. outdated source for fintech information?

4. **Define fintech product specificity:**
   - Bitcoin interest (and its decline) does not directly validate demand for a specific fintech application (e.g., remittances, trading, savings, custody)
   - Narrow hypothesis to a concrete use case and test it with prospective users, not attention proxies

---

## Data Provenance

- **Tool:** wikipedia-interest research CLI v0.x
- **Period:** 24 complete calendar months (Sept 1, 2024 – Aug 31, 2026)
- **Source:** Wikimedia REST API (canonical monthly pageview aggregates)
- **Query:** Q131723 (Bitcoin, Wikidata entity)
- **Methodology:** Normalized Theil–Sen slope (robust trend), latest 3-month YoY (recent growth), month-of-year averages (seasonal), MAD anomaly detection
- **Chart:** Complete source monthly totals; absolute traffic (not normalized by language edition population or market size)

---

## Conclusion

Wikipedia evidence **does not support** a hypothesis of growing B2C fintech opportunity in Spanish-speaking markets based on Bitcoin attention alone. The Spanish edition shows sustained decline since a November 2024 peak, with 60%+ YoY contraction in recent months. Before investing in a B2C fintech product targeting these markets, validate:

1. Whether the decline reflects market saturation, shifting information sources, or reduced consumer interest
2. Where and how your target users currently research fintech solutions
3. Whether demand exists for your specific fintech use case (independent of general Bitcoin interest)
4. Regulatory and competitive landscape in your target geography

**Wikipedia attention is a leading indicator of information-seeking behavior, not demand. Early hypothesis validation requires direct user research.**

---

*Analysis generated: 2026-09-26*  
*Research period: Sept 2024 – Aug 2026 (24 complete months)*  
*Language editions: Spanish (complete), English (unavailable)*
