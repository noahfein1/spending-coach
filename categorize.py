import json
import re
from pathlib import Path
from langchain_ollama import OllamaLLM
import pandas as pd

# Where we cache merchant → category mappings so we
# never ask the LLM the same question twice
CACHE_FILE = Path("category_cache.json")

# The 10 categories the LLM must choose from.
# Keeping it to a fixed list prevents the LLM from
# inventing categories like "Miscellaneous Lifestyle"
CATEGORIES = [
    "Food & Dining",
    "Groceries",
    "Transport",
    "Shopping",
    "Entertainment",
    "Health & Fitness",
    "Bills & Utilities",
    "Travel",
    "Personal Care",
    "Other",
]


def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)


def build_prompt(merchant: str) -> str:
    """
    Enhanced prompt with examples of real bank description formats.
    """
    categories_list = "\n".join(f"- {c}" for c in CATEGORIES)
    return f"""You are a bank transaction categorizer. Classify this transaction into exactly one category.

Bank transaction descriptions are often messy. Here are examples:
- "VENMO PAYMENT 260410 1049511985691 NOAH FEIN" → Other (peer transfer)
- "WHOLEFDS MKT #10201" → Groceries
- "SQ *CHIPOTLE" → Food & Dining
- "SHELL OIL 57444842306" → Transport
- "APPLE CASH BALANCE 1INFINITELOOP" → Other (cash transfer)
- "DOORDASH DASHPASS" → Food & Dining
- "NETFLIX.COM" → Entertainment
- "CVS PHARMACY" → Personal Care
- "UBER TRIP" → Transport
- "AMAZON.COM" → Shopping

Transaction to classify: {merchant}

Categories:
{categories_list}

Rules:
- Reply with ONLY the category name, nothing else
- VENMO, ZELLE, CASH APP payments between people → Other
- Bank transfers and money movements → Other
- If unsure, pick the closest match

Category:"""


def clean_llm_response(response: str) -> str:
    """
    LLMs sometimes add punctuation or extra text even when told not to.
    This strips it and falls back to 'Other' if nothing matches.
    """
    response = response.strip().strip(".")

    # Check if the response matches one of our categories exactly
    for cat in CATEGORIES:
        if cat.lower() in response.lower():
            return cat

    return "Other"


def categorize_merchant(merchant: str, llm: OllamaLLM, cache: dict) -> str:
    """
    Categorize a single merchant string.
    Checks cache first — only calls LLM on cache miss.
    """
    # Normalize the key so "CHIPOTLE #1042" and "CHIPOTLE #2201"
    # both hit the same cache entry
    cache_key = re.sub(r"[#\d]+", "", merchant).strip()

    if cache_key in cache:
        return cache[cache_key]

    prompt = build_prompt(merchant)
    response = llm.invoke(prompt)
    category = clean_llm_response(response)

    # Save to cache immediately so partial runs aren't lost
    cache[cache_key] = category
    save_cache(cache)

    return category


def categorize_transactions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Main entry point. Takes a cleaned DataFrame from ingest.py,
    adds a 'category' column, returns the enriched DataFrame.

    Runs Llama3.2 locally via Ollama — nothing leaves your machine.
    """
    llm = OllamaLLM(model="llama3.2")
    cache = load_cache()

    # Get unique merchants only — no point calling LLM for duplicates
    unique_merchants = df["description"].unique()
    total = len(unique_merchants)

    print(f"Categorizing {total} unique merchants (cache has {len(cache)} entries)...")

    merchant_to_category = {}
    for i, merchant in enumerate(unique_merchants):
        category = categorize_merchant(merchant, llm, cache)
        merchant_to_category[merchant] = category

        # Progress indicator
        if (i + 1) % 10 == 0 or (i + 1) == total:
            print(f"  {i + 1}/{total} done")

    df["category"] = df["description"].map(merchant_to_category)

    print(f"Done. Categories assigned: {df['category'].value_counts().to_dict()}")
    return df