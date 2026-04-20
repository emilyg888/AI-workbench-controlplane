from __future__ import annotations

import streamlit as st

from .. import data


def render() -> None:
    st.header("Home")

    st.subheader("Active bundles")
    cols = st.columns(len(data.list_envs()))
    for i, env in enumerate(data.list_envs()):
        dep = data.get_active_full(env)
        with cols[i]:
            st.metric(env, dep.active_bundle_id or "—")
            st.caption(f"Activated: {dep.activated_at or '—'}")

    st.subheader("Recent runs")
    runs = data.list_runs(limit=5)
    if runs:
        st.dataframe([
            {"run_id": r["run_id"], "bundle_id": r["bundle_id"],
             "status": r["status"],
             "aggregate": r.get("aggregate_score")}
            for r in runs
        ], use_container_width=True)
    else:
        st.caption("No runs yet.")

    st.subheader("Recent promotion decisions")
    decisions = data.promotion_log()[-5:][::-1]
    if decisions:
        st.dataframe([
            {"decision_id": d["decision_id"], "bundle_id": d["bundle_id"],
             "result": d["result"], "approver": d.get("approver")}
            for d in decisions
        ], use_container_width=True)
    else:
        st.caption("No promotion decisions yet.")

    st.subheader("Doctor")
    try:
        report = data.doctor_report()
        if report.ok and not report.issues:
            st.success("All checks pass")
        else:
            for issue in report.issues:
                fn = {"error": st.error, "warn": st.warning,
                      "info": st.info}.get(issue.severity, st.info)
                fn(f"{issue.check}: {issue.message}")
    except Exception as e:
        st.info(f"Doctor unavailable: {e}")
