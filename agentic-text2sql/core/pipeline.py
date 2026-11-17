"""
Pipeline orchestrator — ties all 9 agents together.
Every step records what it received and returned in `trace`.

Usage:
    from core.pipeline import run
    result = run("Show top 10 CSE students", use_rag=True, use_validation=True, use_optimizer=True)
"""
import sys, os, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(override=True)

import config
import agents.schema_agent     as schema_agent
import agents.sql_agent        as sql_agent
import agents.validator_agent  as validator_agent
import agents.optimizer_agent  as optimizer_agent
import agents.executor_agent   as executor_agent
import agents.result_processor as result_processor
import agents.explainer_agent  as explainer_agent


def _step(name, fn, *args, **kwargs):
    """Run one agent step and display diagnostic timing."""
    print(f"\n[START] {name}", flush=True)
    t0 = time.time()
    out = fn(*args, **kwargs)
    elapsed = round(time.time() - t0, 3)
    print(f"[DONE] {name} - {elapsed}s", flush=True)
    return {"step": name, "output": out, "time_s": elapsed}


def run(question,
        use_rag=True,
        use_validation=True,
        use_optimizer=True,
        model=None):
    """
    Returns dict:
        sql, optimized_sql, columns, rows, explanation,
        insights, chart, attempts, error, trace
    """
    trace   = []
    schema  = None     # cached schema dict for validator

    # ── step 1: schema / RAG ──────────────────────────────────────────────────
    s1 = _step("schema_rag", schema_agent.run, question, use_rag=use_rag)
    trace.append(s1)
    context = s1["output"]["context"]

    # ── steps 3+4: generation + validation loop ───────────────────────────────
    sql      = None
    error    = None
    attempts = 0
    s4       = {"output": {"valid": True}}
    max_tries = config.MAX_RETRIES if use_validation else 1

    for attempt in range(max_tries):
        attempts += 1

        # step 3: generate
        s3 = _step("sql_generation", sql_agent.run, question, context, error, sql)
        trace.append(s3)
        sql = s3["output"]["sql"]

        if not use_validation:
            break

        # step 4: validate
        if schema is None:
            schema = validator_agent.get_schema()
        s4 = _step("sql_validation", validator_agent.run, sql, schema, use_explain=True)
        trace.append(s4)

        if s4["output"]["valid"]:
            break
        error = s4["output"]["error"]
        # loop: regenerate with the error fed back

    final_sql = sql

    # ── step 5: optimizer ────────────────────────────────────────────────────
    optimized_sql = final_sql
    if use_optimizer and (not use_validation or s4["output"]["valid"]):
        s5 = _step("sql_optimization", optimizer_agent.run, final_sql, context)
        trace.append(s5)
        optimized_sql = s5["output"]["optimized_sql"]

    run_sql = optimized_sql or final_sql

    # ── step 6: execute ───────────────────────────────────────────────────────
    s6 = _step("execution", executor_agent.run, run_sql)
    trace.append(s6)
    exec_out = s6["output"]

    if exec_out["error"]:
        return {
            "sql":           final_sql,
            "optimized_sql": optimized_sql,
            "columns":       [],
            "rows":          [],
            "explanation":   "",
            "insights":      [],
            "chart":         None,
            "attempts":      attempts,
            "error":         exec_out["error"],
            "trace":         trace,
        }

    columns = exec_out["columns"]
    rows    = exec_out["rows"]

    # ── step 7: result processing ─────────────────────────────────────────────
    s7 = _step("result_processing", result_processor.run, columns, rows)
    trace.append(s7)
    rp = s7["output"]

    # ── step 8: explanation ───────────────────────────────────────────────────
    s8 = _step("explanation", explainer_agent.run,
               question, run_sql, columns, rows,
               rp["df"], rp["num_cols"], rp["cat_cols"])
    trace.append(s8)
    exp_out = s8["output"]

    # ── step 9: final response ────────────────────────────────────────────────
    return {
        "sql":           final_sql,
        "optimized_sql": optimized_sql if optimized_sql != final_sql else None,
        "columns":       columns,
        "rows":          rows,
        "explanation":   exp_out["explanation"],
        "insights":      exp_out["insights"],
        "chart":         exp_out["chart"],
        "attempts":      attempts,
        "error":         None,
        "trace":         trace,
    }
