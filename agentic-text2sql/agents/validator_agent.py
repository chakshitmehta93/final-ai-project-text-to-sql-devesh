"""
SQL validation agent — step 4 of the pipeline.
Input : sql string, schema dict
Output: {"valid": bool, "error": str|None, "sql": str}
Blocks INSERT/UPDATE/DELETE/DROP. Single SELECT only.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.validator import validate
from sqlalchemy import create_engine, inspect
import config


def get_schema():
    engine = create_engine(config.DATABASE_URL)
    insp   = inspect(engine)
    return {t: [c["name"] for c in insp.get_columns(t)] for t in insp.get_table_names()}


def run(sql, schema=None, use_explain=True):
    if schema is None:
        schema = get_schema()
    engine = create_engine(config.DATABASE_URL) if use_explain else None
    try:
        validate(sql, schema, engine=engine)
        return {"valid": True, "error": None, "sql": sql}
    except ValueError as e:
        return {"valid": False, "error": str(e), "sql": sql}
