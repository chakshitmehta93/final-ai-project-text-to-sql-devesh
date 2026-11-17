import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
import requests

import config
from core.llm import ColabBackend, OllamaBackend


def test_colab_ngrok_gateway_error_has_recovery_instructions(monkeypatch):
    response = requests.Response()
    response.status_code = 503
    response._content = b"ngrok gateway error ERR_NGROK_3004"

    monkeypatch.setattr(requests, "post", lambda *args, **kwargs: response)
    backend = ColabBackend(
        base_url="https://example.ngrok-free.dev",
        api_token="test-token",
    )

    with pytest.raises(RuntimeError, match="Restart the model-serving cell"):
        backend.generate(
            "You are an SQL assistant.\n\n"
            "Table: employees (id INTEGER, name TEXT, salary INTEGER)\n"
            "Question: Find names of employees with salary over 50000\n"
            "Write the SQL query:"
        )


def test_missing_finetuned_ollama_model_has_export_instructions(monkeypatch):
    response = requests.Response()
    response.status_code = 404

    def missing_model(*args, **kwargs):
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(requests, "post", missing_model)
    backend = OllamaBackend(model=config.OLLAMA_FINETUNED_MODEL)

    with pytest.raises(RuntimeError, match="Train and export it using the README"):
        backend.generate("SELECT 1")


def test_missing_upstream_ollama_model_has_pull_instructions(monkeypatch):
    response = requests.Response()
    response.status_code = 404

    def missing_model(*args, **kwargs):
        raise requests.exceptions.HTTPError(response=response)

    monkeypatch.setattr(requests, "post", missing_model)
    backend = OllamaBackend(model="qwen2.5-coder:7b")

    with pytest.raises(RuntimeError, match="ollama pull qwen2.5-coder:7b"):
        backend.generate("SELECT 1")


def test_colab_extract_schema_and_question_with_rag_examples():
    """Ensure RAG few-shot examples containing 'Question:' do not swallow the real question."""
    prompt = (
        "You are an expert SQL assistant.\n\n"
        "Database schema:\n  students(student_id, name, dept_id)\n\n"
        "Similar solved examples:\n"
        "Question: How many students are there?\n"
        "SQL: SELECT COUNT(*) FROM students;\n\n"
        "Question: Show top 10 students from CSE who scored above 80\n\n"
        "Write the SQL query:"
    )
    schema_text, question = ColabBackend._extract_schema_and_question(prompt)
    assert question == "Show top 10 students from CSE who scored above 80"
    assert "students(student_id, name, dept_id)" in schema_text
    assert "How many students are there?" in schema_text

