"""
Explanation agent — step 8 of the pipeline.
Uses the LLM (or deterministic stats when using a SQL-only remote endpoint)
to produce a plain-English explanation + key insights.
Also picks the best Plotly chart for the result shape.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from core.llm import get_llm
from core.prompts import explanation_prompt
import plotly.express as px
import pandas as pd


def _pick_chart(df, num_cols, cat_cols):
    """
    Auto-select chart type from result shape:
      - 1 cat + 1 num  → bar chart
      - 1 num only     → histogram
      - 2+ num         → scatter
      - cat only       → pie of value counts
      - date + num     → line chart
    Returns a plotly Figure or None.
    """
    if df is None or df.empty:
        return None

    n_rows = len(df)
    date_cols = [c for c in cat_cols
                 if any(k in c.lower() for k in ["date", "year", "month", "day", "semester"])]

    try:
        if date_cols and num_cols:
            fig = px.line(df, x=date_cols[0], y=num_cols[0],
                          title=f"{num_cols[0]} over {date_cols[0]}")
        elif len(cat_cols) >= 1 and len(num_cols) >= 1 and n_rows <= 50:
            fig = px.bar(df, x=cat_cols[0], y=num_cols[0],
                         title=f"{num_cols[0]} by {cat_cols[0]}",
                         color_discrete_sequence=["steelblue"])
        elif len(num_cols) == 1 and not cat_cols:
            fig = px.histogram(df, x=num_cols[0],
                               title=f"Distribution of {num_cols[0]}",
                               color_discrete_sequence=["steelblue"])
        elif len(num_cols) >= 2:
            fig = px.scatter(df, x=num_cols[0], y=num_cols[1],
                             title=f"{num_cols[0]} vs {num_cols[1]}",
                             color_discrete_sequence=["steelblue"])
        elif cat_cols and not num_cols and n_rows <= 20:
            counts = df[cat_cols[0]].value_counts().reset_index()
            counts.columns = [cat_cols[0], "count"]
            fig = px.pie(counts, names=cat_cols[0], values="count",
                         title=f"Distribution of {cat_cols[0]}")
        else:
            return None

        fig.update_layout(margin=dict(t=40, b=20, l=20, r=20))
        return fig
    except Exception:
        return None


def _parse_insights(text):
    """Extract bullet lines starting with '-' from LLM output."""
    lines = text.split("\n")
    insights = [l.lstrip("- •*").strip() for l in lines if l.strip().startswith("-")]
    if not insights:
        import re
        insights = re.findall(r'\d+\.\s+(.+)', text)
    return insights[:4]


def _local_explanation(question, columns, rows, df, num_cols, cat_cols):
    """
    Fast deterministic explanation + insights used when the backend is a
    fine-tuned SQL-only model (e.g. Colab Qwen 1.5B SQL adapter) or if LLM fails.
    """
    n = len(rows)
    if n == 0:
        return (
            f"The query for '{question}' executed successfully and returned 0 matching rows.",
            ["No records matched the filter criteria in the database."],
        )

    explanation = (
        f"The query answered \"{question}\" and returned {n} row{'s' if n != 1 else ''} "
        f"across {len(columns)} column{'s' if len(columns) != 1 else ''} ({', '.join(columns)})."
    )

    insights = []
    if n == 1 and len(columns) == 1:
        insights.append(f"Result value for {columns[0]}: {rows[0][0]}")
    else:
        insights.append(f"Total records returned: {n}")

    if df is not None and not df.empty:
        for nc in num_cols[:2]:
            col_series = pd.to_numeric(df[nc], errors="coerce").dropna()
            if not col_series.empty:
                insights.append(
                    f"{nc}: average = {col_series.mean():.2f}, "
                    f"min = {col_series.min():.2f}, max = {col_series.max():.2f}"
                )
        if cat_cols and num_cols:
            c_col, n_col = cat_cols[0], num_cols[0]
            top_row = df.loc[pd.to_numeric(df[n_col], errors="coerce").idxmax()]
            insights.append(f"Highest {n_col} is {top_row[n_col]} ({top_row[c_col]})")
        elif cat_cols:
            c_col = cat_cols[0]
            top_vals = df[c_col].astype(str).head(3).tolist()
            insights.append(f"Sample {c_col} values: {', '.join(top_vals)}")

    return explanation, insights[:4]


def run(question, sql, columns, rows, df, num_cols, cat_cols):
    """
    Returns dict: {explanation, insights, chart}
    """
    chart = _pick_chart(df, num_cols, cat_cols)

    # If using the remote Colab SQL-only model or smart_local, generate explanation locally
    # so we don't send English prose prompts to a SQL-only endpoint.
    if config.LLM_BACKEND.strip().lower() in ("colab", "smart_local"):
        explanation, insights = _local_explanation(question, columns, rows, df, num_cols, cat_cols)
        return {"explanation": explanation, "insights": insights, "chart": chart}

    try:
        llm = get_llm()
        prompt = explanation_prompt(question, sql, columns, rows)
        raw = llm.generate(prompt, max_tokens=300)
        lines = [l.strip() for l in raw.strip().split("\n") if l.strip()]
        explanation = next((l for l in lines if not l.startswith("-")), raw.strip())
        insights = _parse_insights(raw)
        if not insights:
            _, insights = _local_explanation(question, columns, rows, df, num_cols, cat_cols)
    except Exception:
        explanation, insights = _local_explanation(question, columns, rows, df, num_cols, cat_cols)

    return {"explanation": explanation, "insights": insights, "chart": chart}
