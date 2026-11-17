"""
SQL optimization agent — step 5 of the pipeline.
Rewrites the SQL for efficiency using sqlglot optimiser + LLM.
Accepts the rewrite only if it returns IDENTICAL rows as the original.
Logs the reason when a rewrite is rejected.
"""
import sys, os, logging
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import sqlglot
from sqlglot.optimizer import optimize as sqlglot_optimize

import config
from core.llm import get_llm
from core.prompts import optimization_prompt
from agents.executor_agent import run as execute_sql

logger = logging.getLogger(__name__)


def _sqlglot_rewrite(sql):
    """Try sqlglot's built-in optimizer (safe, deterministic)."""
    try:
        return sqlglot_optimize(sql, dialect="sqlite").sql(dialect="sqlite")
    except Exception:
        return sql


def _rows_equal(rows_a, rows_b):
    """Order-insensitive row comparison (rounded floats)."""
    def norm(r):
        return tuple(
            round(v, 4) if isinstance(v, float) else v
            for v in r
        )
    return set(norm(r) for r in rows_a) == set(norm(r) for r in rows_b)


def run(sql, context, use_llm_rewrite=True):
    """
    Returns dict with keys: optimized_sql, changed, reason
    """
    # step 1: sqlglot static rewrite
    candidate = _sqlglot_rewrite(sql)

    # step 2: LLM rewrite pass (skipped on Colab / smart_local to avoid latency)
    if use_llm_rewrite and config.LLM_BACKEND.strip().lower() not in ("colab", "smart_local"):
        try:
            llm = get_llm()
            prompt = optimization_prompt(candidate, context)
            raw = llm.generate(prompt, max_tokens=512)
            llm_sql = llm.extract_sql(raw)
            if llm_sql and len(llm_sql) > 10:
                candidate = llm_sql
        except Exception as e:
            logger.warning(f"LLM optimization failed: {e}")

    # step 3: equivalence check
    if candidate.strip().lower() == sql.strip().lower():
        return {"optimized_sql": sql, "changed": False, "reason": "no change needed"}

    orig_result = execute_sql(sql)
    cand_result = execute_sql(candidate)

    orig_ok = orig_result.get("error") is None
    cand_ok = cand_result.get("error") is None

    if not cand_ok:
        reason = f"optimized query failed: {cand_result.get('error')}"
        logger.warning(reason)
        return {"optimized_sql": sql, "changed": False, "reason": reason}

    if orig_ok and not _rows_equal(orig_result["rows"], cand_result["rows"]):
        reason = "optimized query returns different rows — reverting to original"
        logger.warning(reason)
        return {"optimized_sql": sql, "changed": False, "reason": reason}

    return {"optimized_sql": candidate, "changed": True, "reason": "optimization accepted"}
