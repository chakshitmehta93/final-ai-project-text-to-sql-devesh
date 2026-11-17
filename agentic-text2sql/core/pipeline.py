
"""
Pipeline orchestrator for Agentic Text-to-SQL.

Pipeline:
1. Schema / RAG retrieval
2. CSP structural planning
3. SQL generation
4. SQL validation and retry
5. SQL optimization
6. SQL execution
7. Result processing
8. Explanation
"""

import sys
import os
import time
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv(override=True)

from sqlalchemy import create_engine, inspect

import config

import agents.schema_agent as schema_agent
import agents.sql_agent as sql_agent
import agents.validator_agent as validator_agent
import agents.optimizer_agent as optimizer_agent
import agents.executor_agent as executor_agent
import agents.result_processor as result_processor
import agents.explainer_agent as explainer_agent

from core.csp_solver import CSPSolver


# =========================================================
# STEP HELPER
# =========================================================

def _step(name, fn, *args, **kwargs):
    """Run one pipeline step and record execution time."""

    print(f"\n[START] {name}", flush=True)

    t0 = time.time()
    out = fn(*args, **kwargs)

    elapsed = round(time.time() - t0, 3)

    print(f"[DONE] {name} - {elapsed}s", flush=True)

    return {
        "step": name,
        "output": out,
        "time_s": elapsed
    }


# =========================================================
# CSP PLANNING
# =========================================================

def _run_csp(question):
    """
    Load database schema and foreign keys,
    then execute the CSP structural planner.
    """

    engine = None

    try:
        engine = create_engine(config.DATABASE_URL)
        inspector = inspect(engine)

        # Load database schema.
        schema = {
            table: [
                column["name"]
                for column in inspector.get_columns(table)
            ]
            for table in inspector.get_table_names()
        }

        # Load foreign-key relationships.
        foreign_keys = []

        for table in inspector.get_table_names():

            for fk in inspector.get_foreign_keys(table):

                for column, ref_column in zip(
                    fk["constrained_columns"],
                    fk["referred_columns"]
                ):

                    foreign_keys.append({
                        "table": table,
                        "column": column,
                        "ref_table": fk["referred_table"],
                        "ref_column": ref_column
                    })

        solver = CSPSolver(schema, foreign_keys)

        result = solver.solve(question)

        return result

    except Exception as e:

        return {
            "success": False,
            "message": f"CSP planning error: {str(e)}",
            "variables": {},
            "plan": None,
            "trace": []
        }

    finally:
        if engine is not None:
            engine.dispose()


# =========================================================
# FORMAT CSP PLAN FOR THE SQL GENERATION MODEL
# =========================================================

def _format_csp_context(csp_result):
    """
    Convert the structured CSP result into readable
    instructions for the SQL generation model.
    """

    if not csp_result or not csp_result.get("success"):

        message = (
            csp_result.get("message", "No CSP plan available.")
            if csp_result
            else "CSP did not return a result."
        )

        return f"""
CSP STRUCTURAL PLANNING:
No valid CSP plan was produced.

Reason: {message}

Use the retrieved database schema, business rules,
and foreign-key information from the RAG context.
Do not invent tables, columns, or JOIN relationships.
"""

    plan = csp_result["plan"]

    plan_json = json.dumps(
        plan,
        indent=2,
        ensure_ascii=False
    )

    return f"""
==================================================
CSP STRUCTURAL PLAN
==================================================

The following plan was produced by the Constraint
Satisfaction Problem (CSP) planning stage.

Use this plan as structural guidance while generating SQL.

CSP PLAN:
{plan_json}

INSTRUCTIONS:

1. Use the selected fields and their corresponding tables
   when they are relevant to the question.

2. Use the selected JOIN relationships provided by CSP.
   Do not invent foreign-key relationships.

3. Apply the business-rule filters specified in the plan.

4. Respect the planned aggregations, calculated expressions,
   GROUP BY, ORDER BY, and LIMIT operations.

5. Generate a single valid SQLite SELECT query.

6. Check the complete RAG schema context as well.
   The CSP plan is structural guidance, not a replacement
   for schema validation.

7. If the plan does not cover a requirement in the question,
   use the actual database schema and valid relationships
   rather than inventing database fields.

==================================================
END OF CSP STRUCTURAL PLAN
==================================================
"""


# =========================================================
# MAIN PIPELINE
# =========================================================

def run(
    question,
    use_rag=True,
    use_validation=True,
    use_optimizer=True,
    model=None
):
    """
    Returns:
        sql
        optimized_sql
        columns
        rows
        explanation
        insights
        chart
        attempts
        error
        trace
    """

    trace = []
    schema = None

    # -----------------------------------------------------
    # STEP 1: SCHEMA AND RAG RETRIEVAL
    # -----------------------------------------------------

    s1 = _step(
        "schema_rag",
        schema_agent.run,
        question,
        use_rag=use_rag
    )

    trace.append(s1)

    context = s1["output"]["context"]

    # -----------------------------------------------------
    # STEP 2: CSP STRUCTURAL PLANNING
    # -----------------------------------------------------

    s2 = _step(
        "csp_planning",
        _run_csp,
        question
    )

    trace.append(s2)

    csp_result = s2["output"]

    csp_context = _format_csp_context(csp_result)

    # Add CSP plan to the existing RAG context.
    # This context is passed to the existing SQL agent.
    context = context + "\n\n" + csp_context

    # -----------------------------------------------------
    # STEP 3 AND 4: SQL GENERATION + VALIDATION
    # -----------------------------------------------------

    sql = None
    error = None
    attempts = 0

    s4 = {
        "output": {
            "valid": True
        }
    }

    max_tries = (
        config.MAX_RETRIES
        if use_validation
        else 1
    )

    for attempt in range(max_tries):

        attempts += 1

        # STEP 3: SQL generation.
        s3 = _step(
            "sql_generation",
            sql_agent.run,
            question,
            context,
            error,
            sql
        )

        trace.append(s3)

        sql = s3["output"]["sql"]

        if not use_validation:
            break

        # STEP 4: SQL validation.
        if schema is None:
            schema = validator_agent.get_schema()

        s4 = _step(
            "sql_validation",
            validator_agent.run,
            sql,
            schema,
            use_explain=True
        )

        trace.append(s4)

        if s4["output"]["valid"]:
            break

        error = s4["output"]["error"]

        # Retry SQL generation with the validation error.

    final_sql = sql

    # -----------------------------------------------------
    # STEP 5: SQL OPTIMIZATION
    # -----------------------------------------------------

    optimized_sql = final_sql

    if use_optimizer and (
        not use_validation
        or s4["output"]["valid"]
    ):

        s5 = _step(
            "sql_optimization",
            optimizer_agent.run,
            final_sql,
            context
        )

        trace.append(s5)

        optimized_sql = s5["output"]["optimized_sql"]

    run_sql = optimized_sql or final_sql

    # -----------------------------------------------------
    # STEP 6: SQL EXECUTION
    # -----------------------------------------------------

    s6 = _step(
        "execution",
        executor_agent.run,
        run_sql
    )

    trace.append(s6)

    exec_out = s6["output"]

    if exec_out["error"]:

        return {
            "sql": final_sql,
            "optimized_sql": optimized_sql,
            "columns": [],
            "rows": [],
            "explanation": "",
            "insights": [],
            "chart": None,
            "attempts": attempts,
            "error": exec_out["error"],
            "trace": trace
        }

    columns = exec_out["columns"]
    rows = exec_out["rows"]

    # -----------------------------------------------------
    # STEP 7: RESULT PROCESSING
    # -----------------------------------------------------

    s7 = _step(
        "result_processing",
        result_processor.run,
        columns,
        rows
    )

    trace.append(s7)

    rp = s7["output"]

    # -----------------------------------------------------
    # STEP 8: EXPLANATION
    # -----------------------------------------------------

    s8 = _step(
        "explanation",
        explainer_agent.run,
        question,
        run_sql,
        columns,
        rows,
        rp["df"],
        rp["num_cols"],
        rp["cat_cols"]
    )

    trace.append(s8)

    exp_out = s8["output"]

    # -----------------------------------------------------
    # FINAL RESPONSE
    # -----------------------------------------------------

    return {
        "sql": final_sql,

        "optimized_sql": (
            optimized_sql
            if optimized_sql != final_sql
            else None
        ),

        "columns": columns,
        "rows": rows,

        "explanation": exp_out["explanation"],
        "insights": exp_out["insights"],
        "chart": exp_out["chart"],

        "attempts": attempts,
        "error": None,

        "trace": trace
    }
