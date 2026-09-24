Monthly aggregation
- Source data: daily pageviews.
- Reporting unit: complete calendar month.
- Primary monthly measure: total monthly views.
- Supporting measures: average daily views, median daily views, observed_days, expected_days.
- Incomplete boundary months are excluded from trend calculations.
- Internal missing days are never imputed as zero.

Growth
- Do not use first-month vs last-month as headline growth.
- Primary growth metric for the default 24-month window:
  latest 3 complete months vs the same 3 calendar months one year earlier.
- Also expose same-month YoY values where available.
- If comparable YoY history is unavailable, growth is not considered seasonally controlled.

Trend direction
- Use Theil–Sen slope on complete monthly totals as the robust long-range trend indicator.
- Normalize slope by mean or median monthly traffic for cross-series interpretability.
- Do not classify direction from slope alone when strong seasonality is present.
- Combine robust slope direction with YoY direction.

Seasonality
- Detect obvious recurring month-of-year patterns.
- If strong seasonality is present:
  - prefer YoY comparisons;
  - mark simple linear trend as supporting only;
  - describe the topic as seasonal rather than simply increasing/decreasing when appropriate.

Spike detection
- Use robust anomaly detection only after checking for seasonality and low-volume series.
- MAD may be used as a candidate detector for non-seasonal, sufficiently dense series.
- Flag anomalies; do not permanently remove them.

Anomaly sensitivity
- Recalculate trend metrics excluding flagged anomaly days.
- Compare direction and magnitude with the original metrics.
- Report whether the conclusion is:
  unchanged / weaker / stronger / reversed / inconclusive.

Evidence quality
- Do not use a single black-box score.
- Base evidence on:
  data completeness,
  comparable history length,
  agreement between robust trend and YoY,
  seasonality,
  anomaly sensitivity,
  low-volume/noise warnings.

Insufficient evidence
- unresolved topic/article identity;
- missing requested language mapping;
- insufficient comparable history for seasonal interpretation;
- severe internal data gaps;
- known title-history discontinuity;
- trend signals strongly disagree after anomaly handling.

Document the agreed methodology after the product contract is defined.

## Deterministic analysis conventions (implementation slice 3)

These choices define numeric diagnostics only. Interpretation, direction labels,
seasonality classification and evidence levels above are deferred.

- Every calendar month intersecting the requested period is returned. Totals are
  sums of observed days only; means and medians also use observed days only.
  With no observations, these three values are `None`, not zero. Completeness
  requires all calendar days, including observed zero-view days.
- Growth is `(new - old) / old`, expressed as a fraction, with exact old/new
  month lists. `None` plus a reason denotes unavailable comparisons. First/last
  3- and 6-month comparisons average the first/last N available complete source
  months (not necessarily contiguous) and require nonoverlapping windows: at
  least 6 or 12 complete months respectively. First/last requires two months.
- Latest-three-month YoY anchors to the last full calendar month inside the
  requested range. It compares the contiguous three-month window ending there
  with those exact months one year earlier, using averages of monthly totals.
  A missing/incomplete month in either window makes the comparison unavailable;
  it never shifts backward to hide a gap. A partial boundary month is not an anchor.
- OLS uses `sum((x-mean(x))*(y-mean(y))) / sum((x-mean(x))**2)`, where x is elapsed
  calendar months and y is complete monthly totals. Gaps do not compress time.
  Theil–Sen is the median of all pairwise calendar-month slopes. Both need two
  complete months. Both are normalized by **mean monthly total views**, for
  comparable units (fraction per month); a zero mean makes normalization unavailable.
  This settles the previous mean-or-median ambiguity for this slice. The robust
  numerator remains resistant to isolated outliers, but mean normalization is not.
- Daily diagnostics use all observed days, including incomplete months, without
  seasonal adjustment or any claim that their assumptions hold for the series.
  Z-score uses population standard deviation and strict `abs(z) > 3`.
  IQR uses `statistics.quantiles(..., method="inclusive")`; strict flags lie outside
  `[Q1 - 1.5*IQR, Q3 + 1.5*IQR]`. MAD uses the median absolute deviation from the
  median, with `modified_z = 0.67448975*(value-median)/MAD` and strict absolute
  threshold 3.5. IQR flags have no standardized score. See
  [Python statistics definitions](https://docs.python.org/3/library/statistics.html)
  and [NIST modified z-score guidance](https://www.itl.nist.gov/div898/handbook/eda/section3/eda35h.htm).
- Fewer than two days or a zero method-specific dispersion returns that diagnostic
  as unavailable with no flags, not as proof of an anomaly-free series. No fallback
  scale or arbitrary low-volume cutoff is introduced.
- Sensitivity excludes MAD-flagged days only within originally complete months.
  It keeps those same months, recomputes retained-day totals and daily averages,
  and marks the buckets `adjusted=True`. Totals remain audit data only. The
  diagnostic after-trend uses `average_daily_views` of retained observations so
  removing days does not mechanically reduce the trend input through shorter
  exposure. The diagnostic before-trend likewise uses daily averages of the
  original complete months, allowing a comparison in the same units.
  Both use `SensitivityTrend`: raw slope units are views/day per calendar month,
  and each fit is normalized by its own unweighted mean of monthly daily averages.
  Headline `AnalysisResult.trend` remains based on complete monthly TOTAL views;
  its raw slopes must not be compared directly with sensitivity raw slopes.
  Affected adjusted buckets remain incomplete but enter the diagnostic fit;
  incomplete source months remain excluded. No extrapolation, imputation, or
  replacement zeros are used. Adjusted buckets and excluded dates remain available.
  If a month loses every observation, after-trend is unavailable rather than changing
  the month set. If MAD is unavailable, after-trend is unavailable too. Source points
  and buckets are never changed. The result includes before/after OLS and Theil–Sen.
- Month-of-year descriptors average the daily averages of complete source months,
  weighting each contributing year equally (including leap-year Februaries).
  Counts and distinct years accompany all twelve descriptors; absent values are
  `None`. Annual-comparison availability means **at least one** calendar month
  repeats across two years, not that two full years are available or seasonality
  has been established. Per-month counts expose the narrower coverage.

Open interpretation questions remain: when seasonal/low-volume assumptions allow
using anomaly flags, how material a sensitivity difference is, and how much repeated
calendar coverage warrants conclusions. No thresholds for these are implemented.
