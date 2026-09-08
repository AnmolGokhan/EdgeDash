"""Read-only Streamlit dashboard for verified EdgeDash activity."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Callable

import streamlit as st

import edgedash.storage as storage
from edgedash.config import load_config


logger = logging.getLogger(__name__)
_GITHUB_URL = "https://github.com/AnmolGokhan/EdgeDash"


def _redact_secrets(value: str) -> str:
    redacted = value
    for name in ("DATABASE_URL", "GEMINI_API_KEY", "APIFY_TOKEN", "OLLAMA_URL"):
        secret = os.getenv(name)
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def _log_error(message: str, error: Exception) -> None:
    logger.error("%s: %s: %s", message, type(error).__name__, _redact_secrets(str(error)))


st.set_page_config(page_title="EdgeDash Activity", page_icon="ED", layout="wide")


@st.cache_data(ttl=30)
def read_dashboard(path: str) -> dict:
    passing = storage.get_latest_passing_cycle(path)
    latest = storage.get_latest_cycle_summary(path)
    activity = storage.get_cycle_activity(path, limit=30)
    if passing is None:
        return {"passing": None, "latest": latest, "activity": activity, "data": None}
    data = storage.get_passing_cycle_data(path, passing["finished_at"])
    return {"passing": passing, "latest": latest, "activity": activity, "data": data}


def _status(value: str | None) -> str:
    return value or "no cycles yet"


def _safe_panel(name: str, render: Callable[[], None]) -> None:
    try:
        render()
    except Exception as error:
        _log_error(f"Dashboard panel failed: {name}", error)
        st.warning(f"{name} is temporarily unavailable.")


def _empty_cycle_message(hours: int) -> str:
    scheduled = datetime.now(timezone.utc) + timedelta(hours=hours)
    return f"no cycles yet — first run is scheduled for {scheduled:%Y-%m-%d %H:%M UTC}"


def _render_summary(dashboard: dict, fetch_interval_hours: int) -> None:
    passing = dashboard["passing"]
    latest = dashboard["latest"]
    data = dashboard["data"]
    if passing is None or data is None:
        st.info(_empty_cycle_message(fetch_interval_hours))
        return

    current_status = _status(latest["status"] if latest else None)
    st.caption(f"Last successful cycle: {passing['finished_at']} | Verdict: {current_status}")
    if latest and latest["id"] != passing["id"]:
        st.warning(
            "The newest cycle did not pass verification. "
            f"Showing earlier verified data from {passing['finished_at']}."
        )
    first, second, third = st.columns(3)
    first.metric("Total listings", data["total_listings"])
    second.metric("Total scored", data["total_scored"])
    third.metric("Current verdict", current_status)


def _render_activity(activity: list[dict]) -> None:
    if not activity:
        st.info("no cycles yet")
        return
    for row in activity:
        status = str(row.get("status") or "unknown")
        with st.container(border=True):
            timestamp = row.get("finished_at") or row.get("started_at") or "unknown time"
            message = f"{status.upper()} | {timestamp}"
            if status in {"failed", "degraded", "partial"}:
                st.error(message)
            else:
                st.success(message)
            notes = _redact_secrets(str(row.get("notes") or "No details recorded."))
            st.caption(f"Duration/details: {notes}")


def _render_verified_tables(data: dict | None) -> None:
    left, right = st.columns(2)
    with left:
        st.subheader("Top 10 scored listings")
        listings = (data or {}).get("listings", [])
        if listings:
            st.dataframe(listings, use_container_width=True, hide_index=True)
        else:
            st.info("no cycles yet")
    with right:
        st.subheader("Current top 10 skill gaps")
        gaps = (data or {}).get("gaps", [])
        if gaps:
            st.dataframe(gaps, use_container_width=True, hide_index=True)
        else:
            st.info("no cycles yet")


def _render_footer(passing: dict | None) -> None:
    timestamp = passing["finished_at"] if passing else "No successful cycle yet"
    st.caption(f"Last successful cycle: {timestamp} | [GitHub repository]({_GITHUB_URL})")


def main() -> None:
    try:
        config = load_config()
        if not os.getenv("DATABASE_URL"):
            st.title("EdgeDash Activity")
            st.error("database not configured")
            _render_footer(None)
            return
        dashboard = read_dashboard(config.db_path)
    except Exception as error:
        _log_error("Dashboard startup/read failed", error)
        st.title("EdgeDash Activity")
        st.error("database unavailable. Please try again later.")
        _render_footer(None)
        return

    st.title("EdgeDash Activity")
    _safe_panel(
        "Summary",
        lambda: _render_summary(dashboard, int(config.fetch_interval_hours)),
    )

    st.header("Agent Activity Log")
    _safe_panel("Agent activity", lambda: _render_activity(dashboard["activity"]))

    _safe_panel("Verified results", lambda: _render_verified_tables(dashboard["data"]))
    _render_footer(dashboard["passing"])


if __name__ == "__main__":
    main()