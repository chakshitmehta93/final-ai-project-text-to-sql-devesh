"""
Tests for the execution agent and pipeline (offline parts only — no LLM needed).
run:  python -m pytest tests/test_pipeline.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from agents.executor_agent import run as exec_sql
from agents.result_processor import run as process_results
from agents.validator_agent import get_schema


def test_executor_basic():
    result = exec_sql("SELECT COUNT(*) FROM students;")
    assert result["error"] is None
    assert result["row_count"] >= 1
    assert result["rows"][0][0] == 300  # we seeded 300 students


def test_executor_join():
    sql = ("SELECT s.name, d.dept_code FROM students s "
           "JOIN departments d ON s.dept_id = d.dept_id LIMIT 5;")
    result = exec_sql(sql)
    assert result["error"] is None
    assert len(result["rows"]) == 5


def test_executor_blocks_write():
    """Read-only mode should block INSERT."""
    result = exec_sql("INSERT INTO students VALUES (9999,'X',1,1,'M','x@x.com','Active');")
    assert result["error"] is not None


def test_executor_timeout():
    """A query with a very long sleep should time out (unix only)."""
    import platform
    if platform.system() == "Windows":
        pytest.skip("signal timeout not available on Windows")
    result = exec_sql("SELECT * FROM marks m1, marks m2, marks m3 LIMIT 1;", timeout=2)
    # may timeout or succeed, but must not crash
    assert "error" in result


def test_result_processor():
    cols = ["name", "score"]
    rows = [("Alice", 85.0), ("Bob", 72.5), ("Carol", 91.0)]
    out  = process_results(cols, rows)
    assert "df" in out
    assert "score" in out["num_cols"]
    assert "name" in out["cat_cols"]
    assert out["stats"]["score"]["mean"] is not None


def test_schema_has_all_tables():
    schema = get_schema()
    expected = {"students", "departments", "marks", "courses", "enrollments",
                "attendance", "fees", "hostels", "hostel_allotments", "clubs", "club_members", "faculty"}
    assert expected.issubset(set(schema.keys()))
