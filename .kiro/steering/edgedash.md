# EdgeDash Project Steering

## Project Overview

EdgeDash is an autonomous AI career intelligence agent. It runs on a schedule,
fetches live job listings, scores them for fit against a user profile, surfaces
skill gaps, verifies its own output, and publishes results to a Streamlit dashboard.

## Architecture

Do not deviate from this pipeline without discussing it first:

```
Trigger (scheduled)
  -> Orchestrator
    -> Fetcher        (fetches raw job listings)
    -> Scorer         (scores listings against profile)
    -> GapAnalyzer    (identifies skill gaps)
  -> Verifier         (checks output correctness)
  -> Storage          (persists results)
  -> Dashboard        (read-only Streamlit UI)
```

- The Orchestrator reads state and delegates work. It never fetches or scores directly.
- Each sub-agent has exactly one goal and one stop condition.

## Hard Rules

1. **Python 3.11+.** Standard library first. Before adding any third-party
   dependency, explain what real work it saves. Get confirmation before adding it.

2. **Single storage module.** All database access goes through one storage module
   with a thin interface. No other module may import `sqlite3` (or any DB driver)
   directly. The design must support swapping SQLite for hosted Postgres in a
   one-file change (week 4 target).

3. **No hardcoded user data.** Role, city, keywords, skills profile, and any
   other user-specific values must live in config — never inline in code.

4. **No secrets in code.** All secrets and credentials are loaded from environment
   variables. Loading happens in exactly one place.

5. **Cycle logging is mandatory.** Every agent run must write a row to the
   `cycle_log` table recording: what ran, when, how many records were touched,
   pass/fail status, and any retry reason.

6. **Fail loudly.** No bare `except: pass` or silent swallowing of errors.
   Exceptions should propagate or be re-raised with context so failures are
   visible immediately.

7. **Type hints on every function signature.** Docstrings only where the intent
   is not obvious from the function name.

8. **Files stay under ~150 lines.** Split a module before it approaches that
   limit — don't let it become a problem first.

## Network & Sources

9. **Every external source lives behind a `Source` class with a uniform
   interface.** The Fetcher never contains source-specific parsing logic.
   Adding a new source must never require editing the Fetcher.

10. **Every `Source` returns a list of normalised dicts with exactly these
    keys:** `source`, `external_id`, `title`, `company`, `location`, `url`,
    `description`, `posted_at`, `raw`. Missing values are `None` — never
    empty string, never `"N/A"`.

11. **All network calls go through one shared helper** that enforces a 10 s
    timeout (default), 2 retry attempts with exponential backoff, and a
    `User-Agent` header. No bare `requests.get` anywhere else in the codebase.

12. **A source failing must never kill the cycle.** Catch errors per-source,
    log the failure to `cycle_log` with `status="failed"`, and continue to
    the next source. One dead job board must not stop the others.

13. **Secrets come from environment variables loaded via a `.env` file that
    is gitignored.** Never a literal key in code, never a key in
    `config.yaml`. If a required key is missing, that source skips itself
    with a clear log line — it does not crash the cycle.

14. **Respect the source.** Rate-limit to at most 1 request per second per
    source, set a real `User-Agent`, and honour any documented page limits.

## Intelligence & Scoring

15. **All LLM calls go through one module, `edgedash/llm.py`**, exposing one
    function. The provider and model name come from config, never hardcoded.
    Rate-limit to stay inside a free tier (default 1 request per second,
    max 15 per minute). No other file imports an LLM SDK.

16. **Never ask a model for a final score, ranking, or numeric rating.** The
    model extracts structured facts only. All scoring arithmetic is
    deterministic Python in one function. The model never sees the scoring
    weights.

17. **Every model response is validated against an explicit schema before
    use.** A response that fails validation is retried once, then logged as
    a failure for that listing only — it must not crash the cycle or stop
    the remaining listings. Never `json.loads` raw model text without a
    validation and repair path.

18. **Scoring is idempotent.** Never re-score a listing that already has a
    score. Select only listings `WHERE fit_score IS NULL`. Cache extraction
    results keyed on a hash of the job description so the same text is never
    sent to the model twice.

19. **Every score carries a human-readable reason generated from the score
    components by our code** — never free text written by the model.

20. **Log the score distribution** (count, min, max, mean, spread) to
    `cycle_log` on every scoring run. A run where all scores fall within
    10 points of each other is a suspect run and must be logged as such.

21. **Cap listings scored per cycle at a configurable batch size** (default
    25) so a cost or rate-limit blowup is structurally impossible.

## Style Guidelines

- Small, testable functions over large procedural blocks.
- Plain, readable Python over clever or overly concise Python.
- When asked to build one module, build that module only — do not scaffold the
  whole application unless explicitly asked.
