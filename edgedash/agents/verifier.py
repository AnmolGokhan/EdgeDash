"""Deterministic plausibility verifier; it never repairs pipeline data."""

from __future__ import annotations

from datetime import datetime, timezone

import edgedash.storage as storage
from edgedash.agents.base import Agent, AgentResult
from edgedash.config import Config
from edgedash.verification import Verdict, run_all_checks


class Verifier:
    name: str = "Verifier"

    def run(
        self,
        config: Config,
        db_path: str,
        goal: str,
        stop_conditions: dict[str, int],
    ) -> AgentResult:
        inputs = storage.get_verification_inputs(db_path)
        verdict: Verdict = run_all_checks(
            inputs["scores"],
            inputs["facts_list"],
            inputs["gaps"],
            inputs["latest_fetch_at"],
            config,
            datetime.now(timezone.utc),
        )
        failed = ", ".join(check.name for check in verdict.failed_checks) or "none"
        status = "ok" if verdict.passed else "failed"
        notes = f"VERDICT: {'pass' if verdict.passed else 'fail'} - failed_checks={failed} - {verdict.summary}"
        return AgentResult(self.name, status, len(inputs["scores"]), notes, verdict)