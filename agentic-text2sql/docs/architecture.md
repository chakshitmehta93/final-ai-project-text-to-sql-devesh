# architecture

## pipeline overview

```mermaid
flowchart TD
    U["User question (plain English)"] --> S2["2: Schema / RAG Agent\n• embed question\n• retrieve tables, FK hints,\n  rules, few-shot examples\n• build compact context"]
    S2 --> S3["3: SQL Generation Agent\n• Ollama LLM (qwen2.5-coder)\n• sql_generation_prompt + context\n• returns SQL in ```sql``` block"]
    S3 --> S4{"4: SQL Validation Agent\n• sqlglot parse\n• SELECT-only check\n• table / column check\n• EXPLAIN dry-run"}
    S4 -->|"invalid (max 3x)"| S3
    S4 -->|valid| S5["5: SQL Optimization Agent\n• sqlglot static rewrite\n• LLM rewrite pass\n• equivalence check (rollback if rows differ)"]
    S5 --> S6["6: Execution Agent\n• SQLAlchemy read-only\n• timeout + row cap\n• returns columns + rows"]
    S6 --> S7["7: Result Processor\n• pandas DataFrame\n• detect numeric / categorical cols\n• basic stats"]
    S7 --> S8["8: Explanation Agent\n• LLM: 1-2 sentence explanation\n• 2-4 key insights\n• auto-pick Plotly chart"]
    S8 --> S9["9: Final Response\n• sql, optimized_sql, columns, rows\n• explanation, insights, chart\n• full trace (all 9 steps)"]
    S9 --> UI["Streamlit UI\n• result on top\n• one expander per step\n• sidebar toggles"]
```

## component map

| file | role |
|------|------|
| `config.py` | all settings (model, DB URL, paths, timeouts) |
| `core/llm.py` | OllamaBackend + HuggingFaceBackend, extract_sql |
| `core/prompts.py` | all prompt templates (shared with finetune) |
| `core/validator.py` | sqlglot parse + forbidden op + schema check |
| `core/pipeline.py` | orchestrator, trace, ties agents 2-9 together |
| `rag/indexer.py` | builds ChromaDB from tables / FK / rules / examples |
| `rag/retriever.py` | queries ChromaDB, builds context string |
| `agents/schema_agent.py` | step 2 |
| `agents/sql_agent.py` | step 3 |
| `agents/validator_agent.py` | step 4 |
| `agents/optimizer_agent.py` | step 5 |
| `agents/executor_agent.py` | step 6 |
| `agents/result_processor.py` | step 7 |
| `agents/explainer_agent.py` | step 8 |
| `app.py` | Streamlit UI |
| `db/create_db.py` | builds 12-table college.db (300 students) |
| `eval/run_eval.py` | eval on 100 Qs, 5 systems (A-E) |

## database schema (12 tables)

```
departments  ←─ students  ←─ enrollments  ←─ marks
                         ←─ attendance
                         ←─ fees
                         ←─ hostel_allotments ←─ hostels
                         ←─ club_members ←─ clubs ←─ faculty
departments  ←─ faculty
departments  ←─ courses  ←─ enrollments
```

## rag collections (ChromaDB)

| collection | documents | use |
|------------|-----------|-----|
| `tables` | 1 per table with schema + sample values | table retrieval |
| `fk_relationships` | 1 per FK with join hint text | join path hints |
| `rules` | 1 per business rule line | rule retrieval |
| `examples` | 1 per question→SQL pair | few-shot retrieval |
