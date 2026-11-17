"""
Tests for the SQL validator.
run:  python -m pytest tests/test_validator.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from core.validator import validate

SCHEMA = {
    "students":    ["student_id", "name", "dept_id", "year", "gender", "email", "status"],
    "departments": ["dept_id", "dept_name", "dept_code", "hod_name", "established_year"],
    "marks":       ["mark_id", "enroll_id", "student_id", "course_id", "score", "grade", "semester"],
    "courses":     ["course_id", "course_name", "course_code", "credits", "dept_id", "course_type", "year"],
}


def test_valid_simple_select():
    sql = "SELECT name FROM students;"
    assert validate(sql, SCHEMA) == sql


def test_valid_join():
    sql = ("SELECT s.name, d.dept_name FROM students s "
           "JOIN departments d ON s.dept_id = d.dept_id;")
    assert validate(sql, SCHEMA)


def test_valid_aggregation():
    sql = "SELECT AVG(score) AS avg_score FROM marks;"
    assert validate(sql, SCHEMA)


def test_blocks_delete():
    with pytest.raises(ValueError, match="Only SELECT"):
        validate("DELETE FROM students;", SCHEMA)


def test_blocks_drop():
    with pytest.raises(ValueError, match="Forbidden|Only SELECT"):
        validate("DROP TABLE students;", SCHEMA)


def test_blocks_insert():
    with pytest.raises(ValueError, match="Only SELECT|Forbidden"):
        validate("INSERT INTO students VALUES (1,'x',1,1,'M','e@e.com','Active');", SCHEMA)


def test_blocks_multiple_statements():
    with pytest.raises(ValueError, match="Exactly one"):
        validate("SELECT 1; SELECT 2;", SCHEMA)


def test_unknown_table():
    with pytest.raises(ValueError, match="Unknown table"):
        validate("SELECT * FROM nonexistent_table;", SCHEMA)


def test_unknown_column():
    with pytest.raises(ValueError, match="Column|not found"):
        validate("SELECT fake_col FROM students;", SCHEMA)


def test_self_correction_simulation():
    """
    Simulate the self-correction loop:
    first SQL has a bad column, second attempt fixes it.
    """
    bad_sql  = "SELECT fake_col FROM students;"
    good_sql = "SELECT name FROM students;"

    # first attempt fails
    with pytest.raises(ValueError):
        validate(bad_sql, SCHEMA)

    # second attempt succeeds
    result = validate(good_sql, SCHEMA)
    assert result == good_sql
