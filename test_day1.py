from ingest import load_transactions
from categorize import categorize_transactions
import pandas as pd

# If you don't have a real CSV yet, this creates a fake one to test with
sample_data = """Transaction Date,Description,Amount
2026-04-01,SQ *CHIPOTLE 1042,-12.50
2026-04-02,WHOLEFDS #10201,-67.30
2026-04-03,UBER TRIP,-18.90
2026-04-04,NETFLIX.COM,-15.99
2026-04-05,CVS PHARMACY,-24.10
2026-04-06,DOORDASH DASHPASS,-9.99
2026-04-07,SHELL OIL 12345,-55.00
2026-04-08,AMAZON.COM,-43.20
"""

with open("test_transactions.csv", "w") as f:
    f.write(sample_data)

# Test ingest
df = load_transactions("test_transactions.csv")
print("\nCleaned transactions:")
print(df)

# Test categorization (make sure Ollama is running first)
df = categorize_transactions(df)
print("\nWith categories:")
print(df[["date", "description", "amount", "category"]])


from analyze import run_analysis

print("\n--- Running analysis ---")
results = run_analysis(df)

print("\nWeekly baselines:")
print(results["weekly"][["week", "category", "total_spent", "baseline", "is_overspend"]])

print("\nOverspending flags:")
print(results["flags"])

print("\nAnomalous transactions:")
print(results["anomalies"][["date", "description", "amount", "category"]])

print("\nWeekly insight:")
print(results["insight"])