# agentic text-to-sql

a multi-agent pipeline that converts plain-english questions into sql, runs them, and explains the results.
no paid apis — runs entirely locally using ollama.

## quick start (3 commands)

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. create the database and build the rag index
python db/create_db.py && python rag/indexer.py

# 3. start the app (requires ollama running in another terminal)
streamlit run app.py
```

**before step 3**, start ollama:
```bash
ollama serve          # in a separate terminal
ollama pull qwen2.5-coder:7b   # first time only (~4 GB)
```

for weaker laptops use the 3b model:
```bash
ollama pull qwen2.5-coder:3b
# then set OLLAMA_MODEL=qwen2.5-coder:3b in config.py or the sidebar
```

---

## architecture

9-agent pipeline — every step is a small independent file:

```
user question
  → 2. schema/rag agent      (retrieves relevant tables, rules, examples via ChromaDB)
  → 3. sql generation agent  (ollama LLM: qwen2.5-coder)
  → 4. sql validation agent  (sqlglot parse + schema check + EXPLAIN)
       ↑ self-correction loop (max 3 attempts if validation fails)
  → 5. optimizer agent       (sqlglot rewrite + LLM pass, rolled back if rows differ)
  → 6. execution agent       (sqlalchemy read-only, timeout, row cap)
  → 7. result processor      (pandas dataframe, type detection, stats)
  → 8. explanation agent     (llm: 1-2 sentence explanation + 2-4 insights)
  → 9. final response        (sql, rows, explanation, plotly chart, full trace)
```

see [docs/architecture.md](docs/architecture.md) for a full mermaid diagram.

## project structure

```
text2sql/
  config.py              all settings (model, db url, paths, timeouts)
  app.py                 streamlit ui
  requirements.txt
  docker-compose.yml     postgres setup
  db/create_db.py        builds 12-table college.db (300 students, ~4500 marks)
  data/
    college.db           seeded sqlite database
    business_rules.md    30 business rules (retrieved by rag)
    examples.json        40 few-shot question→sql pairs
    eval_set.json        102 gold questions (easy/medium/hard)
    chroma/              chromadb vector store
  rag/
    indexer.py           build chromadb from schema + rules + examples
    retriever.py         query chromadb, build context string
  agents/
    schema_agent.py      step 2 — rag retrieval
    sql_agent.py         step 3 — llm sql generation
    validator_agent.py   step 4 — syntax + schema validation
    optimizer_agent.py   step 5 — equivalence-safe rewrite
    executor_agent.py    step 6 — read-only sql execution
    result_processor.py  step 7 — dataframe + type detection
    explainer_agent.py   step 8 — explanation + plotly chart
  core/
    llm.py               ollamabackend + huggingfacebackend
    prompts.py           all prompt templates
    validator.py         sqlglot validation logic
    pipeline.py          orchestrator with trace
  eval/
    run_eval.py          ablation eval (systems a-e)
    results/             per-question json logs + summary.csv
  tests/
    test_validator.py    10 tests (blocks delete/drop/insert, unknown cols)
    test_rag.py          5 tests (retrieval quality)
    test_pipeline.py     6 tests (executor, result processor, schema)
    test_gold_queries.py 102 parametrized tests (every gold query returns rows)
  docs/
    architecture.md      mermaid diagram + component table
    error_analysis.md    failure categories + 5 real examples
  finetune/
    train_lora.py        lora fine-tuning (needs gpu)
    merge.py             merge lora adapter into base model
```

## database schema (12 tables)

| table | rows | description |
|-------|------|-------------|
| departments | 10 | dept_id, dept_name, dept_code (CSE/ME/ECE/CE/IT/BT/CH/MA/PH/MG), hod_name |
| faculty | 60 | name, dept_id, designation, status (Active/On-Leave) |
| students | 300 | name, dept_id, year (1-4), gender (M/F), status |
| courses | 20 | course_name, course_code, credits, dept_id, course_type (Core/Elective/Lab) |
| enrollments | ~4500 | student_id, course_id, semester, status |
| marks | ~4500 | student_id, course_id, score, grade, semester |
| attendance | ~4500 | student_id, course_id, total_classes, attended |
| fees | ~1500 | student_id, semester, amount, paid, status (Paid/Partial/Unpaid) |
| hostels | 4 | hostel_name, gender (M/F), capacity |
| hostel_allotments | ~125 | student_id, hostel_id, room_no, year |
| clubs | 6 | club_name, faculty_id (advisor), status |
| club_members | ~80 | student_id, club_id, role, year |

ambiguous columns on purpose: `name` appears in students + faculty, `year` in students + courses + hostel_allotments + club_members, `status` in 5 tables.

## rag

4 chromadb collections, all embedded with `all-MiniLM-L6-v2`:
- **tables** — 1 doc per table (schema + sample values)
- **fk_relationships** — 1 doc per foreign key (join hint text)
- **rules** — 1 doc per business rule line (30 rules)
- **examples** — 1 doc per few-shot pair (40 examples)

## running the evaluator

```bash
# single system
python eval/run_eval.py --system E --model qwen2.5-coder:7b

# all 5 systems (a=baseline, b=rag only, c=validation only, d=rag+val, e=full)
python eval/run_eval.py --all
```

results saved to `eval/results/` as json + `eval/results/summary.csv`.
comparison chart saved to `docs/ablation_accuracy.png`.

## running tests

```bash
python -m pytest tests/ -v
```

## postgresql setup

```bash
docker-compose up -d
DATABASE_URL=postgresql://text2sql:text2sql@localhost:5432/college python db/create_db.py
DATABASE_URL=postgresql://text2sql:text2sql@localhost:5432/college python rag/indexer.py
DATABASE_URL=postgresql://text2sql:text2sql@localhost:5432/college streamlit run app.py
```

## llm backends

| backend | how to use |
|---------|-----------|
| ollama (default) | `ollama serve && ollama pull qwen2.5-coder:7b` |
| huggingface | set `LLM_BACKEND=huggingface` in config.py (slower, needs torch) |
| fine-tuned model | run `finetune/train_lora.py` on gpu, then `finetune/merge.py`; model auto-loaded from `finetune/out/merged/` |

## limitations

- ollama must be running locally before the app starts
- fine-tuning needs a gpu (see finetune/ — marked clearly, not required)
- eval timing depends on hardware; a full 102-question run on cpu with 3b takes ~30 min
- the optimizer llm rewrite pass sometimes produces worse sql; equivalence check rolls it back safely
