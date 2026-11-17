"""
Execution agent — step 6 of the pipeline.
Runs the SQL read-only with a timeout and row cap.
Works with both SQLite and PostgreSQL.
Uses threading.Timer for timeout so it works inside Streamlit threads too.
"""
import sys, os, threading
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text
import config


def run(sql, timeout=None, max_rows=None):
    """
    Returns dict: {columns, rows, row_count, error}
    Thread-safe: uses threading.Timer instead of signal.alarm so it works
    inside Streamlit (which runs handlers in a non-main thread).
    """
    timeout  = timeout  or config.QUERY_TIMEOUT
    max_rows = max_rows or config.MAX_ROWS

    # build a read-only URL
    url = config.DATABASE_URL
    if "sqlite" in url:
        db_path = config.DB_PATH
        url = f"sqlite:///file:{db_path}?mode=ro&uri=true"

    result_box = {}   # shared dict filled by the worker thread

    def _worker():
        try:
            engine = create_engine(url, connect_args={"check_same_thread": False})
            with engine.connect() as conn:
                if "sqlite" in config.DATABASE_URL:
                    conn.execute(text("PRAGMA query_only = ON"))
                res = conn.execute(text(sql))
                columns = list(res.keys())
                rows    = res.fetchmany(max_rows)
                result_box["ok"] = {
                    "columns":   columns,
                    "rows":      [tuple(r) for r in rows],
                    "row_count": len(rows),
                    "error":     None,
                }
            engine.dispose()
        except Exception as e:
            result_box["err"] = str(e)

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(timeout)

    if t.is_alive():
        # thread still running after timeout — report timeout
        return {"columns": [], "rows": [], "row_count": 0,
                "error": f"Query exceeded {timeout}s timeout"}

    if "err" in result_box:
        return {"columns": [], "rows": [], "row_count": 0,
                "error": result_box["err"]}

    return result_box.get("ok", {
        "columns": [], "rows": [], "row_count": 0,
        "error": "Unknown execution error"
    })
