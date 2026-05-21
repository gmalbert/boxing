"""
KnockOutIQ — Shared page utilities.

sidebar_header()  — display the KnockOutIQ logo large in the sidebar.
                    Call at the top of every sub-page render function.
                    Theme CSS is injected globally by predictions.py using
                    CSS @media (prefers-color-scheme) — no dropdown needed.
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

_LOGO_PATH = Path(__file__).parent.parent / "data_files" / "logo.png"


def sidebar_header() -> None:
    """Display the KnockOutIQ logo prominently in the sidebar.

    Uses st.sidebar.image() so the logo fills the full sidebar width,
    appearing below the navigation links.
    """
    with st.sidebar:
        if _LOGO_PATH.exists():
            st.image(str(_LOGO_PATH), width=150)
        else:
            st.markdown("## 🥊 KnockOutIQ")
