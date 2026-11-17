"""
Result processing — step 7 of the pipeline.
Converts raw rows into a pandas DataFrame, computes basic stats,
detects column types for chart selection.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pandas as pd


def run(columns, rows):
    """
    Returns dict:
      df           — pandas DataFrame
      dtypes       — {col: 'numeric'|'text'|'date'}
      stats        — basic describe dict for numeric cols
      num_cols     — list of numeric column names
      cat_cols     — list of categorical column names
    """
    if not rows or not columns:
        return {
            "df": pd.DataFrame(),
            "dtypes": {},
            "stats": {},
            "num_cols": [],
            "cat_cols": [],
        }

    df = pd.DataFrame(rows, columns=columns)

    # detect types
    dtypes = {}
    num_cols = []
    cat_cols = []
    for col in df.columns:
        # try numeric coercion
        coerced = pd.to_numeric(df[col], errors="coerce")
        if coerced.notna().sum() / max(len(df), 1) >= 0.8:
            df[col] = coerced
            dtypes[col] = "numeric"
            num_cols.append(col)
        else:
            dtypes[col] = "text"
            cat_cols.append(col)

    # basic stats for numeric columns
    stats = {}
    if num_cols:
        desc = df[num_cols].describe().to_dict()
        stats = {col: {k: round(v, 3) for k, v in vals.items()}
                 for col, vals in desc.items()}

    return {
        "df":       df,
        "dtypes":   dtypes,
        "stats":    stats,
        "num_cols": num_cols,
        "cat_cols": cat_cols,
    }
