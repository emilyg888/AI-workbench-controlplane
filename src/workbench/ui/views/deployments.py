from __future__ import annotations

import streamlit as st

from ... import bundle_manager, deployment_state_manager
from ... import rollback as rb
from ...models import BundleState
from .. import data


def render() -> None:
    st.header("Deployments")
    envs = data.list_envs()

    cols = st.columns(len(envs))
    for i, env in enumerate(envs):
        dep = data.get_active_full(env)
        with cols[i]:
            st.subheader(env)
            st.metric("active", dep.active_bundle_id or "—")
            st.caption(f"since {dep.activated_at or '—'}")
            if dep.active_bundle_id and st.button(f"Rollback {env}",
                                                  key=f"rb_{env}"):
                try:
                    rb.rollback(env, reason="UI rollback")
                    st.success("Rolled back")
                    st.rerun()
                except rb.RollbackError as e:
                    st.error(str(e))

    st.divider()
    st.subheader("Deploy a bundle")
    approved_ids = [b.bundle_id for b in bundle_manager.list_bundles()
                    if b.state in (BundleState.APPROVED, BundleState.DEPLOYED)]
    if not approved_ids:
        st.caption("No approved bundles available. Promote one first.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            target_env = st.selectbox("Environment", envs)
        with col2:
            target_bundle = st.selectbox("Bundle", approved_ids)
        if st.button("Deploy"):
            try:
                deployment_state_manager.set_active(
                    target_env, target_bundle, notes="UI deploy",
                )
                st.success(f"{target_env} → {target_bundle}")
                st.rerun()
            except (deployment_state_manager.UnknownEnvironmentError,
                    deployment_state_manager.PreconditionError) as e:
                st.error(str(e))

    st.divider()
    st.subheader("History")
    events = data.deployment_history()
    if events:
        st.dataframe([e.model_dump() for e in events], use_container_width=True)
    else:
        st.caption("No events.")
