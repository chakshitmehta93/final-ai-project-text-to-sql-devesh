"""
Tests for gold SQL queries — every query in eval_set.json
must pass validation and return a non-empty result.
run:  python -m pytest tests/test_gold_queries.py -v
"""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents.executor_agent import run as exec_sql
from agents.validator_agent import run as validate_sql


with open("data/eval_set.json") as f:
    EVAL_SET = json.load(f)


@pytest.mark.parametrize("item", EVAL_SET, ids=[f"{i}_{it['level']}" for i, it in enumerate(EVAL_SET)])
def test_gold_query(item):
    sql  = item["sql"]
    result = validate_sql(sql, use_explain=False)
    assert result["valid"], f"Gold SQL failed validation: {result['error']}\nSQL: {sql}"

    exec_result = exec_sql(sql)
    assert exec_result["error"] is None, \
        f"Gold SQL execution error: {exec_result['error']}\nSQL: {sql}"
    assert exec_result["row_count"] > 0, \
        f"Gold SQL returned no rows: {sql}"
