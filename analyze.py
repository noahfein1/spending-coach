import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest
from langchain_ollama import OllamaLLM
import json
from pathlib import Path

BUDGETS_FILE = Path("budgets.json")
OVERSPEND_THRESHOLD = 0.10  # flag if 10% over budget

DEFAULT_BUDGETS = {
    "Food & Dining":     300,
    "Groceries":         400,
    "Transport":         150,
    "Shopping":          200,
    "Entertainment":     100,
    "Health & Fitness":  80,
    "Bills & Utilities": 300,
    "Travel":            200,
    "Personal Care":     60,
    "Other":             150,
}


def load_budgets() -> dict:
    if BUDGETS_FILE.exists():
        with open(BUDGETS_FILE) as f:
            return json.load(f)
    return DEFAULT_BUDGETS.copy()


def save_budgets(budgets: dict) -> None:
    with open(BUDGETS_FILE, "w") as f:
        json.dump(budgets, f, indent=2)


def get_date_range_label(df: pd.DataFrame) -> tuple[str, str]:
    """
    Returns (period_label, date_range_string) based on actual data dates.
    e.g. ("Apr 1 – Apr 13, 2026", "month-to-date")
    """
    start = df["date"].min()
    end   = df["date"].max()
    days  = (end - start).days

    date_str = f"{start.strftime('%b %-d')} – {end.strftime('%b %-d, %Y')}"

    if days <= 8:
        period = "this week"
    elif days <= 31:
        period = "this month"
    else:
        period = f"the last {days} days"

    return date_str, period


def compute_budget_comparison(df: pd.DataFrame, budgets: dict) -> pd.DataFrame:
    """
    Compare actual spending per category against user-defined monthly budgets.
    Prorates the budget to match the actual date range in the data.

    Returns DataFrame with columns:
        category, actual_spent, budget, prorated_budget,
        pct_of_budget, is_overspend, remaining
    """
    start = df["date"].min()
    end   = df["date"].max()
    days_in_data = max((end - start).days, 1)

    # Prorate: if data covers 15 days, budget is 15/30 of monthly
    prorate_factor = days_in_data / 30

    actual = (
        df.groupby("category")["amount"]
        .sum()
        .reset_index()
        .rename(columns={"amount": "actual_spent"})
    )

    rows = []
    for _, row in actual.iterrows():
        cat = row["category"]
        spent = row["actual_spent"]
        monthly_budget = budgets.get(cat, DEFAULT_BUDGETS.get(cat, 200))
        prorated = monthly_budget * prorate_factor

        rows.append({
            "category":        cat,
            "actual_spent":    round(spent, 2),
            "monthly_budget":  monthly_budget,
            "prorated_budget": round(prorated, 2),
            "pct_of_budget":   round(spent / prorated, 3) if prorated > 0 else 0,
            "is_overspend":    spent > prorated * (1 + OVERSPEND_THRESHOLD),
            "remaining":       round(prorated - spent, 2),
        })

    return pd.DataFrame(rows).sort_values("pct_of_budget", ascending=False)


def detect_anomalous_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Isolation Forest to flag individual transactions that are
    unusually large compared to others in the same category.
    """
    df = df.copy()
    df["is_anomaly"] = False

    for category, group in df.groupby("category"):
        if len(group) < 5:
            continue
        amounts = group["amount"].values.reshape(-1, 1)
        model = IsolationForest(contamination=0.1, random_state=42)
        preds = model.fit_predict(amounts)
        df.loc[group.index, "is_anomaly"] = preds == -1

    return df


def generate_insight(
    df: pd.DataFrame,
    budget_comparison: pd.DataFrame,
    date_range: str,
    period: str,
) -> str:
    """Generate a plain-English spending summary using local Llama."""

    overspent = budget_comparison[budget_comparison["is_overspend"]]

    if overspent.empty:
        return f"You're on track for {period} ({date_range}) — all categories are within your budget. Nice work."

    flag_lines = []
    for _, row in overspent.iterrows():
        pct = round((row["pct_of_budget"] - 1) * 100)
        flag_lines.append(
            f"- {row['category']}: spent ${row['actual_spent']:.2f} "
            f"vs prorated budget ${row['prorated_budget']:.2f} ({pct}% over)"
        )

    # Top transactions in overspent categories
    top_transactions = []
    for cat in overspent["category"].tolist():
        top = df[df["category"] == cat].nlargest(2, "amount")
        for _, t in top.iterrows():
            top_transactions.append(f"  {cat}: {t['description']} ${t['amount']:.2f}")

    prompt = f"""You are a friendly personal finance coach. Write a short spending summary.

Period: {period} ({date_range})

Over-budget categories:
{chr(10).join(flag_lines)}

Largest transactions in those categories:
{chr(10).join(top_transactions)}

Rules:
- 3 sentences max
- Be specific about dollar amounts
- One actionable suggestion
- Friendly, not judgmental
- Plain text only, no bullet points
- Always put spaces around dollar amounts like $ 42.50

Summary:"""

    llm = OllamaLLM(model="llama3.2")
    return llm.invoke(prompt).strip()


def run_analysis(df: pd.DataFrame, budgets: dict = None) -> dict:
    """Main entry point — runs full analysis pipeline."""
    if budgets is None:
        budgets = load_budgets()

    date_range, period = get_date_range_label(df)
    budget_comparison  = compute_budget_comparison(df, budgets)
    df                 = detect_anomalous_transactions(df)
    overspent          = budget_comparison[budget_comparison["is_overspend"]]
    insight            = generate_insight(df, budget_comparison, date_range, period)

    return {
        "budget_comparison": budget_comparison,
        "transactions":      df,
        "overspent":         overspent,
        "insight":           insight,
        "anomalies":         df[df["is_anomaly"]],
        "date_range":        date_range,
        "period":            period,
        "budgets":           budgets,
    }