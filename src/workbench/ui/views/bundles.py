from __future__ import annotations

import streamlit as st

from ... import bundle_manager
from ...models import BundleState
from ...state_machine import InvalidTransitionError
from .. import data


def render() -> None:
    st.header("Bundles")

    col1, col2 = st.columns(2)
    with col1:
        state_filter = st.selectbox(
            "Filter by state", [None] + [s.value for s in BundleState]
        )
    with col2:
        name_filter = st.text_input("Filter by name")

    bundles = data.list_bundles(state=state_filter, name=name_filter or None)
    if not bundles:
        st.caption("No bundles match.")
        return

    for b in bundles:
        with st.expander(f"{b.bundle_id} — state={b.state.value}"):
            st.json(b.model_dump(mode="json"))
            if b.state not in (BundleState.ARCHIVED, BundleState.REJECTED):
                if st.button("Archive", key=f"arch_{b.bundle_id}"):
                    try:
                        bundle_manager.transition_bundle(
                            b.bundle_id, BundleState.ARCHIVED
                        )
                        st.success(f"Archived {b.bundle_id}")
                        st.rerun()
                    except InvalidTransitionError as e:
                        st.error(str(e))

            with st.expander("Lineage"):
                try:
                    st.graphviz_chart(data.lineage_dot(b.bundle_id))
                except Exception as e:
                    st.caption(f"(lineage unavailable: {e})")
