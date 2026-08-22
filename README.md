# EdgeDash

EdgeDash is an autonomous career-intelligence loop that fetches, scores, and gap-analyses job listings daily, then publishes a read-only dashboard so a user can quickly see which roles fit best and which skills are missing.

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
- [ ] Week 2: Scorer and GapAnalyzer fully integrated into the main cycle
- [ ] Week 3: Gap analysis and verification pass
- [ ] Week 4: Storage swap-out for hosted Postgres, dashboard polish

## Setup

Python: 3.11+

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Edit `config.yaml` to match your target role, city, skills, database path, and scoring preferences.
4. Run the cycle:

```bash
python run_cycle.py
```

## Design decisions

- Storage is isolated behind one module so the app can swap SQLite for Postgres in one place without changing other code.
- Listing IDs are stable SHA-256 hashes of source+url so the same job doesn't get duplicated across runs.
- The Orchestrator delegates to agents instead of doing fetch/score work itself so each stage stays small, testable, and replaceable.

## Notes

This repo is intentionally structured around a simple loop: fetch listings, extract facts, score the fits, identify gaps, store results, and present the output to a dashboard. The mock fetcher is there for safe local development and should not be mistaken for the production source layer.
