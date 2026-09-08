# EdgeDash

EdgeDash is a local-first job intelligence loop for career planning. It fetches job listings, extracts structured facts, scores them against your profile, verifies the results, identifies the biggest skill gaps, and exposes everything through a read-only dashboard and a natural-language query layer.

```text
Config -> Orchestrator -> Fetcher / MockFetcher
                     -> Scorer -> Verifier
                     -> GapAnalyzer
                     -> SQLite storage
                     -> Streamlit dashboard + query tools
```

## What it does

- Fetches listings from configured sources, including Arbeitnow and optional Apify-backed jobs.
- Uses a mock fetcher for safe offline development.
- Extracts job facts and required skills with an LLM-backed extraction layer.
- Scores listings against your configured target role, city, seniority, and skill profile.
- Validates cycle quality with deterministic checks for score spread, extraction sanity, and freshness. A small or missing gap sample is reported as insufficient-data warning information and does not fail the cycle.
- Re-evaluates the scorer and gap-analysis tasks once after a successful fetch so planning reflects newly fetched listings.
- Stores cycle logs and verified snapshots through the configured SQLite or Postgres backend. The read-only dashboard keeps the latest passing-cycle snapshot stable while also showing current live database totals.
- Lets you ask natural-language questions like “show my best matches” or “what are my top skill gaps?” using a deterministic tool registry.

## Current project status

- [x] Multi-stage fetch/score/verify/gap loop
- [x] Config-driven job targeting and tuning
- [x] SQLite-backed persistence and cycle logging
- [x] Read-only Streamlit dashboard
- [x] Deterministic skill canonicalization and alias management
- [x] Verification retry/degraded-cycle handling
- [x] Post-fetch replanning and bounded agent timing instrumentation
- [x] Scheduled GitHub Actions execution with manual dispatch
- [x] Natural-language query routing over verified data
- [x] CLI helpers for diagnostics, skill audits, and gap history

## Requirements

- Python 3.11+
- A Gemini API key or a local Ollama endpoint
- A configured target role and city in `config.yaml`

## Setup

1. Create and activate a virtual environment:

```bash
python -m venv .venv
# Windows
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy the example environment file and add your secrets:

```bash
copy .env.example edgedash\.env
```

Then fill in values such as:

- `GEMINI_API_KEY` when using the Gemini provider
- `APIFY_TOKEN` if the Apify source is enabled
- `OLLAMA_URL` if the Ollama provider is used instead of Gemini

The `edgedash/.env` file is gitignored.

For hosted execution, configure `DATABASE_URL` and `GEMINI_API_KEY` as GitHub Actions repository secrets. The workflow runs the database migration and one cycle daily at 00:30 UTC, and can also be started manually from GitHub Actions.

4. Edit `config.yaml` to match your target role, city, skills, and source settings.

## Running a cycle

Run one full cycle:

```bash
python run_cycle.py
```

The planner uses current database state to decide which agents are due. Fetching is followed by one post-fetch replan for scoring and gap analysis. Scoring is bounded by both `scoring_batch_size` and `score_max_seconds`; elapsed agent durations, retry durations, skipped agents, and failed checks are recorded in the orchestrator summary.

Inspect the plan without executing or writing data:

```bash
python run_cycle.py --dry-run
python run_cycle.py --dry-run --explain
```

Force a specific agent when you want to re-run a stage manually:

```bash
python run_cycle.py --force Scorer
python run_cycle.py --force GapAnalyzer
```

## Read-only analysis commands

These commands help inspect current data without changing the cycle state:

```bash
python -m edgedash.diagnose
python -m edgedash.skills --audit --limit 50
python -m edgedash.skills --suggest-aliases --limit 25
python -m edgedash.gaps
python -m edgedash.gaps --trend
python -m edgedash.verdicts
python -m edgedash.verdicts --check score_spread
```

## Dashboard

Start the dashboard separately from the scheduler:

```bash
python -m streamlit run app.py
```

The dashboard reads the latest passing cycle from SQLite and shows:

- the latest passing-cycle snapshot totals alongside live database totals
- the verified top matches and skill gaps from the latest passing-cycle snapshot
- recent cycle activity, including failed, partial, and degraded events

If the newest cycle is not passing verification, the dashboard continues showing the earlier passing snapshot and identifies that the newest cycle did not pass. A `partial` cycle indicates that an agent failed during execution; a `degraded` cycle indicates that verification remained unsuccessful after the available retry path.

## Natural-language query layer

EdgeDash includes a query router in `edgedash/query/ask.py` and a tool registry in `edgedash/query/tools.py` that answers user questions over verified data.

Example usage:

```python
from edgedash.query.ask import ask

print(ask("show my top matches"))
print(ask("what skill gaps should I focus on next?"))
```

Available tools include:

- `best_matches`
- `top_gaps`
- `gap_detail`
- `trend`
- `listing_count`
- `companies_hiring`
- `skill_demand`

The routing layer is intentionally strict: it validates parameters, refuses suspicious or malformed prompts, and only executes known tools.

## Project structure

```text
app.py                 # Streamlit dashboard entry point
run_cycle.py           # CLI entry point for orchestration cycles
config.yaml            # user-owned target profile and tuning config
.edenv.example         # placeholder env template
edgedash/
  config.py            # config loader
  diagnose.py          # listing diagnostics
  gaps.py              # gap snapshot viewer
  llm.py               # provider selection and JSON validation
  orchestrator.py      # state-driven cycle runner
  planning.py          # agent planning logic
  skills.py            # canonical skill audit and alias suggestions
  verdicts.py          # cycle verification history
  storage.py           # SQLite/Postgres persistence and query helpers
  query/
    ask.py             # natural-language query pipeline
    tools.py           # deterministic query tools
  agents/
    fetcher.py         # live listing fetcher
    mock_fetcher.py    # offline-safe mock data source
    scorer.py          # scoring agent
    gap_analyzer.py    # gap analysis agent
    verifier.py        # verification agent
tests/                 # project test suite
```

## Design notes

- Storage is isolated behind one module so it can be swapped from SQLite to a hosted database later without rewriting the rest of the app.
- Listing IDs are stable hashes of source and URL to reduce duplicate listings across runs.
- Skill aliases are explicit and user-owned in `config.yaml`; suggestions are printed for review and are never applied automatically.
- Verification is intentionally conservative: score-spread, extraction-sanity, and freshness failures can trigger one targeted retry, but a second failure degrades the cycle rather than presenting it as verified. Gap-sample size is warning-only because insufficient supporting data is not itself a plausibility failure.
- Cycle summaries record per-agent timing, retry timing, skipped work, failed checks, and the final outcome (`complete`, `partial`, `degraded`, or `nothing_to_do`).
- The application is designed as a read-only decision aid; model calls are limited to extraction and explicit alias review.

## Privacy and release safety

- Never commit `edgedash/.env`, API keys, SQLite databases, extracted job caches, or raw job data.
- Use `.env.example` only as a template.
- Before pushing, check your repository state:

```bash
git ls-files
git status --short --ignored
```

## Contribution

This project is intentionally organized around a simple loop: fetch listings, normalize the data, score fit, identify gaps, verify the output, and expose the results through dashboards and queries. If you want to change the behavior, update the relevant stage in the orchestrator and keep the verification checks honest.
