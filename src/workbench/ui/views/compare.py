from __future__ import annotations

import streamlit as st

from ... import runtime_compare
from .. import data


def render() -> None:
    st.header("Runtime comparison")
    env = st.session_state.get("env", data.list_envs()[0])

    bundles = [b.bundle_id for b in data.list_bundles()]
    if len(bundles) < 2:
        st.caption("Need at least two bundles to compare.")
        return

    col1, col2, col3 = st.columns(3)
    with col1:
        champion = st.selectbox("Champion", bundles)
    with col2:
        challenger = st.selectbox("Challenger", bundles, index=1)
    with col3:
        window = st.number_input("Window (hours)", min_value=1.0, value=24.0)

    if st.button("Compare"):
        report = runtime_compare.compare_env(
            env, champion, challenger, window_hours=window
        )
        c1, c2 = st.columns(2)
        for label, stats, col in [
            ("Champion", report.champion, c1),
            ("Challenger", report.challenger, c2),
        ]:
            with col:
                st.subheader(label)
                if stats is None:
                    st.caption("—")
                else:
                    st.metric("requests", stats.total)
                    st.metric("errors", stats.errors)
                    st.metric("p50 ms", stats.p50_latency_ms)
                    st.metric("p95 ms", stats.p95_latency_ms)
                    st.metric("policy block rate",
                              f"{stats.policy_block_rate:.1%}")
