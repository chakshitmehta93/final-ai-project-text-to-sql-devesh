"""
Tests for the RAG retriever.
run:  python -m pytest tests/test_rag.py -v
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest


def test_retriever_returns_rules():
    from rag.retriever import Retriever
    r = Retriever()
    rules = r.retrieve_rules("show CSE students who scored above 80")
    assert isinstance(rules, list)
    assert len(rules) > 0
    # at least one rule should mention CSE or score
    combined = " ".join(rules).lower()
    assert "cse" in combined or "score" in combined or "dept_code" in combined


def test_retriever_returns_examples():
    from rag.retriever import Retriever
    r = Retriever()
    examples = r.retrieve_examples("top students by average marks")
    assert isinstance(examples, list)
    assert len(examples) > 0
    # examples should contain SQL
    combined = " ".join(examples).upper()
    assert "SELECT" in combined


def test_retriever_returns_fk_hints():
    from rag.retriever import Retriever
    r = Retriever()
    fk = r.retrieve_fk("join students with departments")
    assert isinstance(fk, list)


def test_build_context_with_rag():
    from rag.retriever import Retriever
    r = Retriever()
    ctx, trace = r.build_context("Show top CSE students", use_rag=True)
    assert "departments" in ctx.lower() or "students" in ctx.lower()
    assert isinstance(trace["rules"], list)
    assert isinstance(trace["examples"], list)


def test_build_context_without_rag():
    from rag.retriever import Retriever
    r = Retriever()
    ctx_rag, _    = r.build_context("show students", use_rag=True)
    ctx_no_rag, _ = r.build_context("show students", use_rag=False)
    # without RAG context is shorter (no rules/examples appended)
    assert len(ctx_no_rag) <= len(ctx_rag)
