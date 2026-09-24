# Wikipedia Interest

## Project purpose

An Agent Skill project for exploring Wikipedia pageview interest across topics
and languages, with deterministic Python processing and a thin AI-agent
orchestration layer. Product scope lives in [product_contract.md](product_contract.md).

## Current status

Skeleton only: an installable package, placeholder CLI and modules, and an import
smoke test. The product contract currently contains headings awaiting definition.
Data access, analysis, charts, reports, and the skill workflow are not implemented.

## Local setup

Requires Python 3.12 or newer. From the repository root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
python -m pytest
wikipedia-interest
```

## Planned high-level development stages

1. Define and agree the product contract.
2. Implement data retrieval and topic resolution.
3. Implement deterministic analysis with tests.
4. Add charts and concise shareable reports.
5. Add and evaluate the Agent Skill orchestration workflow.
