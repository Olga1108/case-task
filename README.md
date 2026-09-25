# Wikipedia Interest

Research Wikipedia pageview attention across language editions with deterministic
Python analysis, compact JSON evidence, monthly PNG charts, and one-page PDF briefs. An Agent Skill
handles topic selection and restrained interpretation. Product scope is in
[product_contract.md](product_contract.md). Persistent caching is not implemented.

## Local setup

Requires Python 3.12+:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

Set `WIKIPEDIA_USER_AGENT` to your application name/version and real contact URL
or email before live requests. Alternatively pass `--user-agent` to each command.

## Commands

Discover up to five candidates; the command never selects one:

```sh
wikipedia-interest search --query "intermittent fasting" --query-language en
```

After selecting a retrieved candidate, validate it, map its Wikidata identity, and
research the requested editions in order:

```sh
wikipedia-interest research --query "intermittent fasting" --query-language en \
  --selected-title "Intermittent fasting" --languages cs,uk \
  --start 2024-09-01 --end 2026-08-31
```

Omit dates for the last 24 complete calendar months, excluding the current UTC
month. Use `--months 12` for another complete-month window, or supply both explicit
boundaries. Dates must be on or after 2015-07-01. Add `--expected-qid` with the
previously retrieved Q-ID to pin the identity on follow-ups.

To generate a chart, add `--chart ./attention.png` to the research command. It
writes a PNG at exactly that path; the parent directory must exist. Incomplete
months are gaps, and unavailable languages are skipped. If no complete monthly
data exists or the output cannot be written, `execution.chart_error` explains the
failure while the research evidence remains available.

To generate a shareable one-page report, add `--report ./brief.pdf`. The report
uses the already computed source metrics, complete-month chart semantics, explicit
limitations, and deterministic interpretation templates. Its parent directory
must exist. `--chart` and `--report` may be used together; either artifact can fail
without discarding the research JSON, with details in its corresponding
`execution.*_error` field.

Commands emit one strict JSON document on stdout (except human-readable `--help`).
Shared input/API failures emit `{"error": {"code": "...", "message": "..."}}`
and exit 2. Structured research results exit 0 even with partial/all-language
failures; inspect `workflow_status` and each language. `no_data` and partial
observations remain distinct from API errors. `period` gives effective dates;
`execution.period_mode` records defaults. Summary `warning_ids` are zero-based
indexes into the unique top-level `warnings` list. No daily arrays are emitted.

## Methodology and skill

Wikipedia pageviews measure attention, not demand or willingness to pay. Absolute
edition traffic is not normalized market size. Source trends use complete monthly
totals; anomaly sensitivity uses daily averages without imputing removed days.
See [methodology](references/methodology.md) for units and limitations.

[SKILL.md](SKILL.md) defines discovery, semantic selection, research, interpretation,
and follow-ups. To distribute/install this repository as a skill, use a directory
named `wikipedia-interest-research` containing SKILL.md and its referenced files,
then install its Python package. The directory must match frontmatter `name` under
the [Agent Skills specification](https://agentskills.io/specification); this working
checkout can retain its repository name.

## Tests and evaluation

```sh
python -m pytest -q
```

Unit tests use synthetic data or mocked HTTP, without live Wikimedia requests.
Evaluation datasets live in [evaluation/datasets](evaluation/datasets/).
