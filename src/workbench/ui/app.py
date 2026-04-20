"""Streamlit entrypoint. Run with: workbench ui  (or streamlit run ...)."""
from __future__ import annotations

import streamlit as st

from workbench.ui import data
from workbench.ui.pages import (
    bundles as bundles_page,
)
from workbench.ui.pages import (
    compare as compare_page,
)
from workbench.ui.pages import (
    deployments as deployments_page,
)
from workbench.ui.pages import (
    home as home_page,
)
from workbench.ui.pages import (
    promotions as promotions_page,
)
from workbench.ui.pages import (
    runs as runs_page,
)

PAGES = {
    "Home": home_page.render,
    "Bundles": bundles_page.render,
    "Runs": runs_page.render,
    "Deployments": deployments_page.render,
    "Promotions": promotions_page.render,
    "Compare": compare_page.render,
}


def main() -> None:
    st.set_page_config(page_title="AI Workbench", layout="wide")
    st.sidebar.title("AI Workbench")
    page = st.sidebar.radio("Page", list(PAGES), label_visibility="collapsed")

    envs = data.list_envs()
    if "env" not in st.session_state:
        st.session_state.env = envs[0] if envs else "dev"
    st.sidebar.divider()
    st.sidebar.selectbox("Environment", envs, key="env")

    try:
        report = data.doctor_report()
        if not report.ok:
            st.error(
                f"Doctor flagged {len(report.issues)} issue(s). "
                "See the Home tab."
            )
    except Exception:
        pass

    PAGES[page]()


if __name__ == "__main__":
    main()
