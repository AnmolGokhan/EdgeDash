"""Read-only Streamlit dashboard for verified EdgeDash activity."""

from __future__ import annotations

import streamlit as st

import edgedash.storage as storage
from edgedash.config import load_config


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


def main() -> None:
    config = load_config()
    try:
        dashboard = read_dashboard(config.db_path)
    except Exception as exc:
        st.error(f"Unable to read dashboard data: {exc}")
        return

    passing = dashboard["passing"]
    latest = dashboard["latest"]
    data = dashboard["data"]
    st.title("EdgeDash Activity")
    if passing is None or data is None:
        st.info("no cycles yet")
    else:
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

    st.header("Agent Activity Log")
    activity = dashboard["activity"]
    if not activity:
        st.info("no cycles yet")
    else:
        for row in activity:
            status = str(row.get("status") or "unknown")
            with st.container(border=True):
                if status in {"failed", "degraded", "partial"}:
                    st.error(f"{status.upper()} | {row['finished_at'] or row['started_at']}")
                else:
                    st.success(f"{status.upper()} | {row['finished_at'] or row['started_at']}")
                st.caption(f"Duration/details: {row.get('notes') or 'No details recorded.'}")

    left, right = st.columns(2)
    with left:
        st.subheader("Top 10 scored listings")
        st.dataframe((data or {}).get("listings", []), use_container_width=True, hide_index=True)
    with right:
        st.subheader("Current top 10 skill gaps")
        st.dataframe((data or {}).get("gaps", []), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()