import pandas as pd
from pathlib import Path
import re

# ---------------------------------------------------------------------------
# Column fuzzy-matching patterns
# We check each column name against these patterns to find date/amount/desc
# without caring what the specific bank calls them.
# ---------------------------------------------------------------------------

DATE_PATTERNS = [
    "date", "trans", "posted", "settlement"
]
AMOUNT_PATTERNS = [
    "amount", "debit", "credit", "charge", "payment"
]
DESC_PATTERNS = [
    "description", "desc", "merchant", "payee",
    "name", "memo", "detail", "narrative"
]


def _match_column(columns: list[str], patterns: list[str]) -> str | None:
    """
    Return the first column name whose lowercase version contains
    any of the pattern strings. Returns None if nothing matches.
    """
    for col in columns:
        col_lower = col.lower().strip()
        for pattern in patterns:
            if pattern in col_lower:
                return col
    return None


def _is_date_string(value: str) -> bool:
    """Check if a string looks like a date — used to detect headerless CSVs."""
    try:
        pd.to_datetime(str(value).strip().strip('"'))
        return True
    except Exception:
        return False


def _has_headers(filepath: Path) -> bool:
    """
    Peek at the first cell of the CSV.
    If it parses as a date → no headers (Wells Fargo style).
    If it's a word → has headers (Chase, BoA, etc).
    """
    with open(filepath, "r", encoding="utf-8-sig") as f:
        first_line = f.readline()
    first_cell = first_line.split(",")[0].strip().strip('"')
    return not _is_date_string(first_cell)


def _load_raw(filepath: Path) -> pd.DataFrame:
    if _has_headers(filepath):
        return pd.read_csv(filepath, encoding="utf-8-sig")
    else:
        # Wells Fargo fixed format: date, amount, *, empty, description
        df = pd.read_csv(
            filepath,
            header=None,
            names=["Date", "Amount", "_flag", "_empty", "Description"],
            encoding="utf-8-sig"
        )
        return df[["Date", "Amount", "Description"]]


def _looks_like_amount(value: str) -> bool:
    """Returns True if value looks like a dollar amount: -45.23, $12.00, (10.00)"""
    cleaned = re.sub(r'[\$,"()\s]', '', value)
    try:
        float(cleaned)
        return True
    except Exception:
        return False


def _looks_like_description(value: str) -> bool:
    """Returns True if value looks like a merchant name — has letters, not just numbers."""
    return bool(re.search(r'[A-Za-z]{2,}', value))


def _normalize_amount(series: pd.Series) -> pd.Series:
    """
    Clean amount strings from any bank:
    "$-45.23" → -45.23
    "(45.23)" → -45.23  (some banks use parens for debits)
    "45.23"   →  45.23
    """
    return (
        series.astype(str)
        .str.replace(r'[\$,\s"]', '', regex=True)
        .str.replace(r'\((.+)\)', r'-\1', regex=True)
        .astype(float)
    )


def _resolve_amount(df: pd.DataFrame) -> pd.Series:
    """
    Handle two common bank structures:
    1. Single 'Amount' column where debits are negative
    2. Separate 'Debit' and 'Credit' columns (some BoA / Citi exports)
    Returns a single Series where expenses are NEGATIVE.
    """
    cols_lower = {c.lower(): c for c in df.columns}

    # Check for split debit/credit columns
    debit_key  = next((cols_lower[k] for k in cols_lower if "debit"  in k), None)
    credit_key = next((cols_lower[k] for k in cols_lower if "credit" in k), None)

    if debit_key and credit_key:
        # Debit column = money out → make negative
        # Credit column = money in → keep positive
        debit  = _normalize_amount(df[debit_key].fillna("0"))
        credit = _normalize_amount(df[credit_key].fillna("0"))
        return -debit + credit

    # Single amount column
    amount_col = _match_column(list(df.columns), AMOUNT_PATTERNS)
    if amount_col:
        return _normalize_amount(df[amount_col])

    raise ValueError(
        "Could not find an amount column. "
        "Please make sure your CSV has a column named 'Amount', 'Debit', or similar."
    )


def load_transactions(filepath: str | Path) -> pd.DataFrame:
    """
    Load ANY bank CSV and return a clean, normalized DataFrame.

    Works with:
      - Wells Fargo (no headers, positional columns)
      - Chase, BoA, Capital One, Citi, Amex, Discover
      - Any CSV with date + amount + description columns

    Output always has exactly three columns:
        date        — datetime
        description — str, merchant name uppercased
        amount      — float, POSITIVE number (expenses only, income removed)
    """
    filepath = Path(filepath)
    df = _load_raw(filepath)
    df = df.dropna(how="all")

    # --- Find date column ---
    date_col = _match_column(list(df.columns), DATE_PATTERNS)
    if not date_col:
        raise ValueError(
            "Could not find a date column. "
            "Expected a column named 'Date', 'Transaction Date', etc."
        )
    df["date"] = pd.to_datetime(df[date_col], errors="coerce")
    df = df.dropna(subset=["date"])  # drop rows where date couldn't parse

    # --- Find description column ---
    desc_col = _match_column(list(df.columns), DESC_PATTERNS)
    if not desc_col:
        raise ValueError(
            "Could not find a description column. "
            "Expected a column named 'Description', 'Merchant', 'Payee', etc."
        )
    df["description"] = (
    df[desc_col]
    .astype(str)
    .str.strip()
    .str.strip('"')
    .str.upper()
    .replace("NAN", "UNKNOWN")  # handle empty cells
            )
    df = df[df["description"] != "UNKNOWN"]

    # Clean Wells Fargo verbose descriptions before LLM sees them
    df["description"] = df["description"].str.replace(
        r"PURCHASE AUTHORIZED ON \d{2}/\d{2}\s+", "", regex=True
    )
    df["description"] = df["description"].str.replace(
        r"\s+[SP]\d{12,}\s+CARD\s+\d{4}.*$", "", regex=True
    ).str.strip()

    # --- Resolve amount ---
    df["amount"] = _resolve_amount(df)

    # --- Keep expenses only, flip to positive ---
    df = df[df["amount"] < 0].copy()
    df["amount"] = df["amount"].abs()

# Strip out transfers, payments, and money movements
# These are not expenses — they're just money moving between accounts
    TRANSFER_KEYWORDS = [
        "TRANSFER", "ZELLE", "VENMO PAYMENT", "ONLINE TRANSFER",
        "WIRE TRANSFER", "ACH TRANSFER", "PAYMENT TO", "PAYMENT FROM",
        "MOBILE PAYMENT", "DIRECT DEPOSIT", "PAYROLL", "TAX REFUND",
        "INTEREST PAYMENT", "ATM WITHDRAWAL"
    ]

    pattern = "|".join(TRANSFER_KEYWORDS)
    before = len(df)
    df = df[~df["description"].str.contains(pattern, case=False, na=False)]
    print(f"Removed {before - len(df)} transfer/payment rows, {len(df)} expense transactions remaining")
        # --- Final clean output ---
    df = df[["date", "description", "amount"]].sort_values("date").reset_index(drop=True)

    print(f"Loaded {len(df)} expense transactions from {filepath.name}")
    return df


def load_from_streamlit(uploaded_file) -> pd.DataFrame:
    """Accepts a Streamlit UploadedFile — used by app.py."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".csv") as tmp:
        tmp.write(uploaded_file.read())
        tmp_path = tmp.name
    result = load_transactions(tmp_path)
    os.unlink(tmp_path)
    return result