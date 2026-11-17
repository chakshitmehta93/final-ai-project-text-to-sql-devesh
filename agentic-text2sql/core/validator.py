"""
SQL validation agent.
Checks:
  1. Parse error (sqlglot)
  2. Only a single SELECT statement
  3. No forbidden operations (INSERT/UPDATE/DELETE/DROP/etc.)
  4. Table names exist in the schema
  5. Column names exist in the referenced tables
  6. EXPLAIN dry-run via SQLAlchemy
"""
import sqlglot
from sqlglot import exp

FORBIDDEN = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop,
    exp.Create, exp.Alter, exp.Command, exp.TruncateTable,
)


def validate(sql, schema, engine=None):
    """
    schema: dict  {table_name: [col1, col2, ...]}
    engine: SQLAlchemy engine for EXPLAIN (optional, skipped if None)
    Raises ValueError with a human-readable message on any failure.
    Returns the sql string unchanged on success.
    """
    # 1. parse
    try:
        stmts = sqlglot.parse(sql, read="sqlite")
    except Exception as e:
        raise ValueError(f"Syntax error: {e}")

    if len(stmts) != 1 or stmts[0] is None:
        raise ValueError("Exactly one SQL statement is required.")

    tree = stmts[0]

    # 2. must be SELECT
    if not isinstance(tree, exp.Select):
        raise ValueError("Only SELECT queries are allowed.")

    # 3. forbidden ops anywhere in the tree
    for node in tree.walk():
        n = node[0] if isinstance(node, tuple) else node
        if isinstance(n, FORBIDDEN):
            raise ValueError(f"Forbidden operation detected: {type(n).__name__}")

    # 4. table names
    aliases = {}  # alias -> real table name
    for t in tree.find_all(exp.Table):
        tname = t.name.lower()
        # check against lower-cased schema keys
        schema_lower = {k.lower(): k for k in schema}
        if tname not in schema_lower:
            raise ValueError(
                f"Unknown table '{t.name}'. Available tables: {list(schema.keys())}"
            )
        real = schema_lower[tname]
        aliases[t.alias_or_name.lower()] = real

    # 5. column names
    # collect aliases defined by SELECT expressions  (e.g. AVG(score) AS avg_score)
    select_aliases = {a.alias.lower() for a in tree.find_all(exp.Alias)}

    for col in tree.find_all(exp.Column):
        cname = col.name.lower()
        if cname == "*" or cname in select_aliases:
            continue
        if col.table:
            tkey = col.table.lower()
            real_tbl = aliases.get(tkey)
            if real_tbl is None:
                raise ValueError(f"Unknown table alias '{col.table}'")
            allowed = [c.lower() for c in schema[real_tbl]]
            if cname not in allowed:
                raise ValueError(
                    f"Column '{col.name}' not found in table '{real_tbl}'. "
                    f"Available: {schema[real_tbl]}"
                )
        else:
            # unqualified — accept if it appears in any used table
            used_tables = list(aliases.values())
            found = any(
                cname in [c.lower() for c in schema[t]]
                for t in used_tables
                if t in schema
            )
            if used_tables and not found:
                raise ValueError(
                    f"Column '{col.name}' not found in any referenced table."
                )

    # 6. EXPLAIN dry-run (only when engine is provided)
    if engine is not None:
        from sqlalchemy import text as sa_text
        try:
            with engine.connect() as conn:
                conn.execute(sa_text(f"EXPLAIN QUERY PLAN {sql}"))
        except Exception as e:
            raise ValueError(f"EXPLAIN failed: {e}")

    return sql
