"""MockFetcher — returns realistic fake listings with no network calls.

Four of the twelve listings have stable URLs so duplicate suppression is
demonstrable: run the cycle twice and the NEW count drops from 12 to 8.
"""

from __future__ import annotations

from datetime import date

from edgedash.agents.base import Agent, AgentResult
from edgedash.config import Config
import edgedash.storage as storage


# ---------------------------------------------------------------------------
# Fake data
# ---------------------------------------------------------------------------

# These four are pinned. Same source + url = same SHA-256 id every run.
_STABLE_LISTINGS: list[dict] = [
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-101",
        "title": "Data Analyst",
        "company": "Flipkart",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Work with large-scale e-commerce datasets using SQL and Python. "
            "Build Tableau dashboards for category teams. Requires 2+ years "
            "experience with pandas, data cleaning, and A/B test analysis."
        ),
        "posted_at": "2026-08-15",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-102",
        "title": "Senior Data Analyst",
        "company": "Swiggy",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Own analytics for the supply-chain vertical. Deep SQL, Python "
            "scripting, and experience with Redshift or BigQuery required. "
            "Spark exposure is a strong plus. 4–6 years preferred."
        ),
        "posted_at": "2026-08-14",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-103",
        "title": "Business Analyst",
        "company": "Razorpay",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Translate fintech product metrics into executive narratives. "
            "Advanced Excel, Power BI, and SQL. Exposure to dbt or Looker "
            "is a differentiator. 3+ years in payments or BFSI preferred."
        ),
        "posted_at": "2026-08-13",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-104",
        "title": "Data Analyst – Growth",
        "company": "Meesho",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Support growth and retention experiments. Funnel analysis in "
            "SQL, cohort modelling in Python. Familiarity with Mixpanel or "
            "Amplitude is useful. 1–3 years of experience."
        ),
        "posted_at": "2026-08-12",
    },
]

# These eight vary each run only in that they exist at all (URLs are unique).
_VARIABLE_LISTINGS: list[dict] = [
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-201",
        "title": "Junior Data Analyst",
        "company": "Ola Electric",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Entry-level role on the vehicle telemetry team. Good grasp of "
            "SQL and Excel required. Python and statistics a bonus. "
            "Fresh graduates welcome."
        ),
        "posted_at": "2026-08-16",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-202",
        "title": "Analytics Engineer",
        "company": "PhonePe",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Build and maintain dbt models on top of BigQuery. Write "
            "Python glue pipelines, document data contracts, and mentor "
            "junior analysts. 3+ years, strong SQL fundamentals."
        ),
        "posted_at": "2026-08-16",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-203",
        "title": "Product Analyst",
        "company": "Zepto",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Embedded with the app product team. Define KPIs, run "
            "experiments, and build Power BI reports for leadership. "
            "SQL + Python required, Spark is a nice-to-have. 2–4 years."
        ),
        "posted_at": "2026-08-15",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-204",
        "title": "Lead Data Analyst",
        "company": "Infosys BPM",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Lead a team of 4 analysts supporting an insurance client. "
            "Expert-level SQL, advanced Excel, and stakeholder management. "
            "Tableau certification preferred. 6+ years experience."
        ),
        "posted_at": "2026-08-14",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-205",
        "title": "Data Analyst – Marketing",
        "company": "Myntra",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Attribution modelling and campaign performance analytics. "
            "SQL, Python (pandas, matplotlib), and Google Analytics. "
            "Experience with Looker Studio a plus. 2+ years."
        ),
        "posted_at": "2026-08-13",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-206",
        "title": "Data Analyst – Risk",
        "company": "Lendingkart",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Credit risk scorecard monitoring and portfolio reporting. "
            "Strong SQL and Excel required; Python and statistics essential. "
            "BFSI domain experience preferred. 3–5 years."
        ),
        "posted_at": "2026-08-12",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-207",
        "title": "BI Analyst",
        "company": "Wipro",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Design and maintain Power BI semantic models for an FMCG "
            "client. SQL, DAX, and data modelling required. Python "
            "automation is a strong plus. 2–4 years in BI tools."
        ),
        "posted_at": "2026-08-11",
    },
    {
        "source": "mock",
        "url": "https://jobs.example.com/da-208",
        "title": "Data Analyst – Operations",
        "company": "BigBasket",
        "location": "Bengaluru, Karnataka",
        "description": (
            "Last-mile delivery optimisation and inventory analytics. "
            "SQL and Python for ETL, Tableau for ops dashboards. "
            "Logistics domain experience is a bonus. 1–3 years."
        ),
        "posted_at": "2026-08-10",
    },
]

_ALL_LISTINGS: list[dict] = _STABLE_LISTINGS + _VARIABLE_LISTINGS


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class MockFetcher:
    name: str = "MockFetcher"

    def run(self, config: Config, db_path: str) -> AgentResult:
        new_count = storage.upsert_listings(db_path, _ALL_LISTINGS)
        return AgentResult(
            agent=self.name,
            status="ok",
            records_touched=new_count,
            notes=(
                f"Offered 12 listings ({len(_STABLE_LISTINGS)} stable + "
                f"{len(_VARIABLE_LISTINGS)} variable); {new_count} were new."
            ),
        )
