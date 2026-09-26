# Wikipedia Interest

Research Wikipedia pageview attention across language editions with deterministic
Python analysis, compact JSON evidence, monthly PNG charts, and one-page PDF briefs. An Agent Skill
handles topic selection and restrained interpretation. Product scope is in
[product_contract.md](product_contract.md). Persistent caching is not implemented.

## Install locally

Requires Git and Python 3.12+. Clone the repository, create a virtual environment,
and install the package with its development dependencies:

```sh
git clone https://github.com/Olga1108/case-task.git wikipedia-interest-research
cd wikipedia-interest-research
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
```

On Windows PowerShell, activate the environment with
`.venv\Scripts\Activate.ps1` instead.

Set `WIKIPEDIA_USER_AGENT` to your application name/version and real contact URL
or email before live requests. Do not use a placeholder contact. Alternatively,
pass `--user-agent` to each command.

Confirm the installation:

```sh
wikipedia-interest --help
python -m pytest -q
```

## Use with an agent for research

Open the cloned `wikipedia-interest-research` directory as the agent's current
project/workspace. Make sure `WIKIPEDIA_USER_AGENT` is available in the environment
that launches the agent. Then ask the agent to use the repository's skill explicitly,
for example:

```text
Use the wikipedia-interest-research skill in SKILL.md to research whether interest
in meditation is growing or declining in the English and Spanish Wikipedia editions
over the last 24 complete months. Create a chart and a one-page PDF in this workspace.
```

The agent reads [SKILL.md](SKILL.md), discovers and validates a source article,
pins its Wikidata identity, maps the requested language editions, runs the installed
CLI, and returns deterministic JSON evidence plus any requested artifacts. It uses
`.venv/bin/wikipedia-interest` directly if `wikipedia-interest` is not on its command
path. Generated artifacts stay inside the current workspace unless you explicitly
request another location.

You can refine the same research in follow-up messages, for example:

```text
Add the Polish Wikipedia edition using the same selected topic and period.
```

```text
Re-run the same topic for the last 12 complete months.
```

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
and follow-ups. Its structure follows the
[Agent Skills specification](https://agentskills.io/specification) and OpenAI's
[skill guidance](https://developers.openai.com/plugins/build/skills).

## Tests and evaluation

```sh
python -m pytest -q
```

Unit tests use synthetic data or mocked HTTP, without live Wikimedia requests.
Evaluation datasets live in [evaluation/datasets](evaluation/datasets/).
