# Intermittent fasting — Czech vs Ukrainian

## Evaluation goal

Validate that the `wikipedia-interest-research` skill can:

- discover the correct Wikipedia topic from a natural-language request;
- preserve the same entity across language editions;
- use deterministic analysis;
- handle partial data correctly;
- generate a chart and one-page PDF;
- avoid unsupported market-level conclusions.

## User prompt

> Compare Wikipedia attention for intermittent fasting in Czech and Ukrainian over the last 24 complete months. Tell me what the evidence suggests for an early B2C product hypothesis, and create a one-page PDF brief.

## Evaluation setup

- Model: Claude Haiku 4.5
- Provider: OpenRouter
- Agent environment: OpenCode
- Skill: `wikipedia-interest-research`
- Manual intervention: none

## Resolved topic

- Source article: `Intermittent fasting`
- Wikidata entity: `Q1666254`
- Czech article: `Přerušovaný půst`
- Ukrainian article: `Інтервальне голодування`
- Period: `2024-09-01` to `2026-08-31`

## Deterministic result

### Czech edition

- Data completeness: 22 complete / 2 incomplete months
- Latest 3m YoY: unavailable because required months are incomplete
- Long-range normalized Theil–Sen trend: `-0.0481 / month`
- Direction: `inconclusive`
- Deterministic summary:
  `Recent direction is inconclusive because latest-3m YoY is unavailable; long-range trend is negative.`

### Ukrainian edition

- Data completeness: 23 complete / 1 incomplete months
- Latest 3m YoY: `-37.0%`
- Long-range normalized Theil–Sen trend: `-0.0691 / month`
- Direction: `negative`
- Deterministic summary:
  `Recent YoY and robust long-range trend are both negative.`

## Generated artifacts

- `attention.png`
- `brief.pdf`

The PDF uses the same deterministic direction logic as the compact JSON.

## Cheap-model evaluation

### Result

PASS

### What worked

- Skill was loaded automatically.
- Candidate discovery was performed before research.
- The correct article and Q-ID were selected.
- The same entity was mapped across Czech and Ukrainian editions.
- Partial source data remained explicit.
- Missing recent YoY was not replaced with zero or a fabricated value.
- Chart and PDF were generated successfully.
- Artifacts were stored in the project workspace.
- Wikipedia pageviews were not treated as market size, willingness to pay, or product-market fit.

### Minor observation

The free-form answer contained one slightly stronger cross-edition synthesis sentence than the deterministic per-edition conclusions supported.

The underlying deterministic result remained correct.

## Iteration triggered by evaluation

Earlier runs exposed several weaknesses in lightweight-model behavior:

- inventing or overriding the Wikimedia User-Agent;
- writing artifacts to external temporary directories;
- strengthening an inconclusive direction into a negative conclusion;
- inferring market maturity or saturation;
- collapsing different per-edition states into one shared conclusion.

The skill was updated so that:

- an existing `WIKIPEDIA_USER_AGENT` is reused unchanged;
- artifacts default to the current workspace;
- deterministic `direction.status` and `direction.summary` are produced in Python;
- PDF and compact JSON share the same direction source of truth;
- the model is instructed not to recompute or strengthen direction.

## Conclusion

The case demonstrates that the skill can execute the complete workflow with a low-cost tool-capable model while keeping calculations and evidence interpretation bounded by deterministic Python logic.