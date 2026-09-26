## Evaluation result

## User prompt

Compare Wikipedia attention for Bitcoin in English and Spanish over the last 24 complete months. Tell me what the evidence suggests for an early B2C fintech product hypothesis, and create a one-page PDF brief.

**PARTIAL — functional edge case discovered**

The skill correctly discovered Bitcoin (Q131723), analyzed the Spanish edition,
generated the chart and PDF, and preserved unavailable English evidence.

However, the requested English edition was also the validated source edition.
The mapper incorrectly attempted to resolve it through interlanguage links and
returned `LANGUAGE_SITELINK_MISSING`.

Expected behavior:
- reuse the already validated source page for the source language;
- use langlinks only for other requested editions.

The evaluation also showed that the cheap model can still add unsupported
causal/business explanations in free-form prose, while the deterministic PDF
remains within scope.