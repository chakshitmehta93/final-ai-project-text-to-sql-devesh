"""
All prompt templates in one place.
Shared between inference (pipeline) and fine-tuning (finetune/train_lora.ipynb).
"""

SYSTEM = (
    "You are an expert SQL assistant. Given a database schema and a question, "
    "write a single correct SQLite SELECT query. "
    "Return ONLY the SQL inside a ```sql ... ``` block, nothing else."
)


def sql_generation_prompt(question, schema_context, error=None, prev_sql=None):
    """Build the user-turn prompt for SQL generation."""
    parts = [schema_context, f"\nQuestion: {question}"]
    if error and prev_sql:
        parts.append(
            f"\nThe previous SQL had an error:\nSQL: {prev_sql}\nError: {error}"
            "\nFix the SQL and try again."
        )
    parts.append("\nWrite the SQL query:")
    return SYSTEM + "\n\n" + "\n".join(parts)


def explanation_prompt(question, sql, columns, rows):
    """Prompt for the explanation agent."""
    sample = rows[:5] if rows else []
    return (
        f"Question: {question}\n"
        f"SQL: {sql}\n"
        f"Columns: {columns}\n"
        f"Sample rows (up to 5): {sample}\n\n"
        "1. Write 1-2 clear sentences explaining what this query found.\n"
        "2. List 2-4 key insights as bullet points starting with '-'.\n"
        "Keep it simple and direct."
    )


def optimization_prompt(original_sql, schema_context):
    """Prompt for the optimizer to suggest a better query."""
    return (
        f"{schema_context}\n\n"
        f"Original SQL:\n{original_sql}\n\n"
        "Rewrite this SQL to be more efficient: remove redundant JOINs, "
        "unnecessary DISTINCT, unused columns. Add LIMIT 100 if none exists. "
        "Return ONLY the improved SQL in a ```sql ... ``` block."
    )
