from __future__ import annotations

from pathlib import Path

import streamlit as st

from ... import bundle_manager, promotion_engine
from ...models import BundleState
from ...state_machine import InvalidTransitionError
from .. import data


def render() -> None:
    st.header("Promotions")

    # Pending candidates
    candidates = [b for b in bundle_manager.list_bundles()
                  if b.state == BundleState.CANDIDATE]
    if candidates:
        st.subheader("Pending candidates")
        for b in candidates:
            col1, col2, col3 = st.columns([4, 1, 1])
            col1.write(b.bundle_id)
            if col2.button("Approve", key=f"appr_{b.bundle_id}"):
                try:
                    promotion_engine.approve(b.bundle_id, approver="ui")
                    st.success(f"Approved {b.bundle_id}")
                    st.rerun()
                except InvalidTransitionError as e:
                    st.error(str(e))
            if col3.button("Reject", key=f"rej_{b.bundle_id}"):
                try:
                    promotion_engine.reject(b.bundle_id, reason="UI reject")
                    st.warning(f"Rejected {b.bundle_id}")
                    st.rerun()
                except promotion_engine.PromotionError as e:
                    st.error(str(e))

    st.divider()
    st.subheader("Decision log")
    entries = data.promotion_log()
    if not entries:
        st.caption("No decisions.")
        return

    st.dataframe(entries, use_container_width=True)
    decision_id = st.selectbox(
        "Select a decision for detail",
        [e["decision_id"] for e in entries],
    )
    chosen = next(e for e in entries if e["decision_id"] == decision_id)
    st.json(chosen)

    out_name = st.text_input("Evidence pack filename", f"{decision_id}.zip")
    if st.button("Build evidence pack"):
        try:
            path = data.build_evidence_pack(decision_id, Path(out_name))
            st.success(f"Wrote {path}")
        except Exception as e:
            st.error(str(e))
