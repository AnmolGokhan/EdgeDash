# EdgeDash

EdgeDash is an autonomous career-intelligence loop that fetches, scores, verifies, and gap-analyses job listings, then publishes a read-only dashboard so a user can quickly see which roles fit best and which skills are missing.

```text
Trigger -> Orchestrator -> [Fetcher | Scorer | GapAnalyzer] -> Verifier
      -> Storage -> Dashboard (read-only)
```

## Current status

- [x] Fetcher pipeline and database setup
- [x] Mock Fetcher for offline development (temporary, not production data)
- [x] Extraction cache and structured job-fact extraction
- [x] Deterministic scoring pipeline and tests
- [x] Config-driven tuning and cycle logging
- [x] State-driven planning with dry-run, force, and explain flags
- [x] Deterministic gap analysis with timestamped snapshots and trends
- [x] Verification checks with bounded retry and degraded-cycle handling
- [x] Read-only Streamlit activity dashboard
- [ ] Week 4: Storage swap-out for hosted Postgres, dashboard polish

## Setup

Python: 3.11+

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Copy `.env.example` to `edgedash/.env` and add your Gemini key if using Gemini. The `.env` file is gitignored.
4. Edit `config.yaml` to match your target role, city, skills, database path, and scoring preferences.
5. Run the cycle:

```bash
python run_cycle.py
```

The cycle is state-driven. Inspect the plan without making writes or API calls:

```bash
python run_cycle.py --dry-run
python run_cycle.py --dry-run --explain
python run_cycle.py --force Scorer
```

Useful read-only commands:

```bash
python -m edgedash.diagnose
python -m edgedash.skills --audit --limit 50
python -m edgedash.gaps
python -m edgedash.gaps --trend
python -m edgedash.verdicts
python -m edgedash.verdicts --check score_spread
```

Start the dashboard separately from the scheduler:

```bash
python -m streamlit run app.py
```

The dashboard reads only data from the latest passing cycle. Failed or degraded
cycle activity remains visible in the activity log, but it cannot replace the
last known-good data.

## Design decisions

- Storage is isolated behind one module so the app can swap SQLite for Postgres in one place without changing other code.
- Listing IDs are stable SHA-256 hashes of source+url so the same job doesn't get duplicated across runs.
- The Orchestrator delegates to agents instead of doing fetch/score work itself so each stage stays small, testable, and replaceable.
- Scoring and aggregate analysis are deterministic Python; model calls are limited to fact extraction and explicit alias suggestions.
- Verification checks plausibility rather than pretending to know ground truth. A failed verification gets at most one bounded retry, then the cycle is degraded.
- Skill aliases are explicit, user-owned entries in `config.yaml`; suggestions are printed for review and never applied automatically.

## Notes

This repo is intentionally structured around a simple loop: fetch listings, extract facts, score the fits, identify gaps, store results, and present the output to a dashboard. The mock fetcher is there for safe local development and should not be mistaken for the production source layer.

Duplicate detection is intentionally conservative: if the cross-source duplicate count stays under about 10% of the total listings, leave it alone and note it as a known limitation. This repo does not do fuzzy title matching in week 1; that is a rabbit hole and is not the grading target.

## Privacy and secrets

- Never commit `edgedash/.env`, API keys, SQLite databases, cache files, or job data.
- Use `.env.example` only as a placeholder template.
- Check tracked files before pushing:

```bash
git ls-files
git status --short --ignored
```
