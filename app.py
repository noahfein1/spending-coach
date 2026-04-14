import streamlit as st
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
from ingest import load_from_streamlit
from categorize import categorize_transactions
from analyze import run_analysis, load_budgets, save_budgets, DEFAULT_BUDGETS

st.set_page_config(page_title="Spending Coach", page_icon="💰", layout="wide")

# ── Budget setup (runs once, saves to budgets.json) ──────────────
def show_budget_setup():
    st.title("💰 Welcome to Spending Coach")
    st.markdown("Set your **monthly budget** for each category. You can change these anytime in the sidebar.")

    budgets = DEFAULT_BUDGETS.copy()
    cols = st.columns(2)

    items = list(budgets.items())
    for i, (cat, default) in enumerate(items):
        col = cols[i % 2]
        budgets[cat] = col.number_input(
            f"{cat} ($/month)",
            min_value=0,
            max_value=10000,
            value=default,
            step=10,
            key=f"budget_{cat}"
        )

    st.markdown("")
    if st.button("Save budgets and continue →", type="primary"):
        save_budgets(budgets)
        st.session_state["budgets_set"] = True
        st.rerun()


# Show budget setup on first run
from pathlib import Path
if not Path("budgets.json").exists() and "budgets_set" not in st.session_state:
    show_budget_setup()
    st.stop()

budgets = load_budgets()

# ── Sidebar ──────────────────────────────────────────────────────
with st.sidebar:
    st.title("💰 Spending Coach")
    st.caption("100% local — your data never leaves this machine.")
    st.divider()

    uploaded = st.file_uploader("Upload bank CSV", type="csv")

    if uploaded:
        with st.spinner("Loading transactions..."):
            df_raw = load_from_streamlit(uploaded)
        with st.spinner("Categorizing with AI (first run ~30s)..."):
            df = categorize_transactions(df_raw)
        with st.spinner("Analyzing vs your budget..."):
            results = run_analysis(df, budgets)
        st.session_state["results"] = results
        st.session_state["df"] = df
        st.success(f"Loaded {len(df)} transactions")

    # Budget editor in sidebar
    if st.sidebar.expander("Edit budgets"):
        pass

    with st.sidebar.expander("✏️ Edit monthly budgets"):
        updated = {}
        for cat, amt in budgets.items():
            updated[cat] = st.number_input(
                cat, min_value=0, max_value=10000,
                value=int(amt), step=10, key=f"side_{cat}"
            )
        if st.button("Update budgets"):
            save_budgets(updated)
            budgets = updated
            if "df" in st.session_state:
                st.session_state["results"] = run_analysis(
                    st.session_state["df"], budgets
                )
            st.success("Budgets updated")
            st.rerun()

    # Category correction
    if "df" in st.session_state:
        st.divider()
        st.subheader("Fix a category")
        df_side = st.session_state["df"]
        selected = st.selectbox("Merchant", df_side["description"].unique().tolist())
        new_cat  = st.selectbox("Correct category", list(DEFAULT_BUDGETS.keys()))
        if st.button("Apply correction"):
            st.session_state["df"].loc[
                st.session_state["df"]["description"] == selected, "category"
            ] = new_cat
            st.session_state["results"] = run_analysis(
                st.session_state["df"], budgets
            )
            st.success(f"Updated → {new_cat}")
            st.rerun()

# ── Main dashboard ───────────────────────────────────────────────
if "results" not in st.session_state:
    st.title("💰 Spending Coach")
    st.info("Upload your bank CSV in the sidebar to get started.")
    st.markdown("""
    **How to export your transactions:**
    - **Wells Fargo:** Account Activity → Download → Comma Separated (CSV)
    - **Chase:** Transactions → Download → CSV
    - **Bank of America:** Transaction History → Export → CSV
    """)
    st.stop()

results = st.session_state["results"]
df      = st.session_state["df"]
bc      = results["budget_comparison"]
period  = results["period"]
date_range = results["date_range"]

# ── Insight card ─────────────────────────────────────────────────
st.subheader(f"Summary — {date_range}")
if not results["overspent"].empty:
    st.warning(results["insight"])
else:
    st.success(results["insight"])

st.divider()

# ── Metrics ──────────────────────────────────────────────────────
total_spent  = bc["actual_spent"].sum()
total_budget = bc["prorated_budget"].sum()
remaining    = total_budget - total_spent
n_over       = len(results["overspent"])
n_anomalies  = len(results["anomalies"])

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total spent", f"${total_spent:,.2f}",
            f"${remaining:+,.2f} vs prorated budget")
col2.metric("Prorated budget", f"${total_budget:,.2f}",
            f"for {date_range}")
col3.metric("Over-budget categories", n_over, delta_color="inverse")
col4.metric("Flagged transactions", n_anomalies, delta_color="inverse")

st.divider()

# ── Charts ───────────────────────────────────────────────────────
col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Actual vs budget by category")

    fig = go.Figure()
    bc_sorted = bc.sort_values("actual_spent", ascending=True)

    fig.add_trace(go.Bar(
        y=bc_sorted["category"],
        x=bc_sorted["prorated_budget"],
        name="Prorated budget",
        orientation="h",
        marker_color="#3C3489",
        opacity=0.4
    ))
    fig.add_trace(go.Bar(
        y=bc_sorted["category"],
        x=bc_sorted["actual_spent"],
        name="Actual spent",
        orientation="h",
        marker_color=[
            "#E24B4A" if over else "#639922"
            for over in bc_sorted["is_overspend"]
        ]
    ))
    fig.update_layout(
        barmode="overlay",
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
        height=380,
        legend=dict(orientation="h", y=-0.15)
    )
    st.plotly_chart(fig, use_container_width=True)

with col_right:
    st.subheader("Budget utilization")

    bc["pct_display"] = (bc["pct_of_budget"] * 100).round(1)
    fig2 = px.bar(
        bc.sort_values("pct_of_budget", ascending=True),
        x="pct_display",
        y="category",
        orientation="h",
        color="pct_display",
        color_continuous_scale=["#639922", "#EF9F27", "#E24B4A"],
        range_color=[0, 150],
        labels={"pct_display": "% of budget used", "category": ""},
        height=380
    )
    fig2.add_vline(x=100, line_dash="dash", line_color="gray", opacity=0.5)
    fig2.update_layout(
        plot_bgcolor="rgba(0,0,0,0)",
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=0, r=0, t=10, b=0),
        coloraxis_showscale=False
    )
    st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ── Budget summary table ─────────────────────────────────────────
st.subheader("Budget breakdown")
display_bc = bc.copy()
display_bc["actual_spent"]    = display_bc["actual_spent"].apply(lambda x: f"${x:,.2f}")
display_bc["prorated_budget"] = display_bc["prorated_budget"].apply(lambda x: f"${x:,.2f}")
display_bc["monthly_budget"]  = display_bc["monthly_budget"].apply(lambda x: f"${x:,.2f}")
display_bc["remaining"]       = bc["remaining"].apply(
    lambda x: f"+${x:,.2f}" if x >= 0 else f"-${abs(x):,.2f}"
)
display_bc["pct_of_budget"]   = bc["pct_of_budget"].apply(lambda x: f"{x*100:.0f}%")
display_bc["status"]          = bc["is_overspend"].map({True: "⚠️ Over", False: "✓ On track"})
display_bc = display_bc[[
    "category", "actual_spent", "prorated_budget",
    "monthly_budget", "remaining", "pct_of_budget", "status"
]].rename(columns={
    "category": "Category",
    "actual_spent": "Spent",
    "prorated_budget": "Prorated budget",
    "monthly_budget": "Monthly budget",
    "remaining": "Remaining",
    "pct_of_budget": "% used",
    "status": "Status"
})
st.dataframe(display_bc, use_container_width=True, hide_index=True)

st.divider()

# ── Transactions table ───────────────────────────────────────────
st.subheader("All transactions")
col_a, col_b = st.columns(2)
filter_cat     = col_a.multiselect(
    "Filter by category",
    options=df["category"].unique().tolist(),
    default=df["category"].unique().tolist()
)
show_anomalies = col_b.checkbox("Show flagged only", value=False)

filtered = df[df["category"].isin(filter_cat)].copy()
if "is_anomaly" not in filtered.columns:
    filtered["is_anomaly"] = False
if show_anomalies:
    filtered = filtered[filtered["is_anomaly"]]

display_df = filtered[["date", "description", "amount", "category", "is_anomaly"]].copy()
display_df["date"]   = display_df["date"].dt.strftime("%b %d, %Y")
display_df["amount"] = display_df["amount"].apply(lambda x: f"${x:.2f}")
display_df = display_df.rename(columns={
    "date": "Date", "description": "Merchant",
    "amount": "Amount", "category": "Category",
    "is_anomaly": "Flagged"
})
st.dataframe(display_df, use_container_width=True, hide_index=True)