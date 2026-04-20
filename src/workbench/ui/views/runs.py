from __future__ import annotations

import altair as alt
import pandas as pd
import streamlit as st

from .. import data


def render() -> None:
    st.header("Run / Eval")
    st.caption("Experiments against eval sets, with scorecards")

    runs = data.list_runs(limit=100)
    if not runs:
        st.caption("No runs.")
        return

    df = pd.DataFrame(runs)
    st.dataframe(df[["run_id", "bundle_id", "eval_set", "status",
                     "aggregate_score", "p50_latency_ms", "p95_latency_ms"]],
                 use_container_width=True)

    run_id = st.selectbox("Select a run for detail", df["run_id"].tolist())
    if run_id is None:
        return

    tabs = st.tabs(["Scorecard", "Metrics", "Timings"])
    with tabs[0]:
        card = data.get_scorecard(run_id)
        if card:
            st.markdown(card)
        else:
            st.caption("No scorecard — run `eval <run_id>` first.")

    with tabs[1]:
        metrics = data.get_run_metrics(run_id)
        if metrics:
            scores = metrics.get("scores", {})
            if scores:
                chart_df = pd.DataFrame([
                    {"metric": k, "value": v} for k, v in scores.items()
                ])
                chart = alt.Chart(chart_df).mark_bar().encode(
                    x="metric", y="value"
                )
                st.altair_chart(chart, use_container_width=True)
            st.json(metrics)
        else:
            st.caption("No metrics.")

    with tabs[2]:
        row = next((r for r in runs if r["run_id"] == run_id), None)
        if row:
            st.metric("p50 latency (ms)", row.get("p50_latency_ms") or 0)
            st.metric("p95 latency (ms)", row.get("p95_latency_ms") or 0)
            st.metric("succeeded", row.get("succeeded") or 0)
            st.metric("failed", row.get("failed") or 0)
