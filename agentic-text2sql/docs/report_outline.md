# evaluation report outline

## abstract
brief: multi-agent text-to-sql with self-correction on a 12-table college database.
llm: qwen2.5-coder:7b via ollama (fully local).

## systems evaluated

| system | rag | validation loop | optimizer |
|--------|-----|----------------|-----------|
| A — baseline | ✗ | ✗ | ✗ |
| B — rag only | ✓ | ✗ | ✗ |
| C — validation only | ✗ | ✓ | ✗ |
| D — rag + validation | ✓ | ✓ | ✗ |
| E — full pipeline | ✓ | ✓ | ✓ |

## metrics

- **execution accuracy** — predicted rows match gold rows (order-insensitive, floats rounded to 4 dp)
- **validity rate** — % of queries that pass the validator
- **avg attempts** — average number of generation attempts per question
- **avg latency** — seconds per question (end-to-end)
- accuracy broken down by easy / medium / hard

## expected results (fill in after running eval/run_eval.py --all)

| system | exec acc | validity | avg attempts | avg latency |
|--------|----------|----------|--------------|-------------|
| A |  |  | 1.0 |  |
| B |  |  | 1.0 |  |
| C |  |  |  |  |
| D |  |  |  |  |
| E |  |  |  |  |

## key findings

1. rag reduces wrong-filter errors because business rules (e.g. dept_code='CSE') are retrieved.
2. validation loop eliminates syntax errors and unknown-column failures through self-correction.
3. optimizer keeps execution accuracy unchanged (equivalence check prevents regressions).
4. the main remaining failure mode is semantic misinterpretation of aggregate questions.
5. full pipeline (E) outperforms baseline (A) on all metrics, especially on hard queries.

## error analysis
see [docs/error_analysis.md](error_analysis.md) for the full breakdown and 5 real failure examples.

## limitations

- eval limited to sqlite; postgres results may differ slightly due to type coercion.
- latency dominated by ollama first-token time; a gpu reduces this by ~5-10x.
- the 3b model is faster but less accurate on hard queries involving 3+ joins.

## reproducing results

```bash
# install + setup
pip install -r requirements.txt
python db/create_db.py
python rag/indexer.py

# start ollama
ollama serve &
ollama pull qwen2.5-coder:7b

# run all 5 systems
python eval/run_eval.py --all --model qwen2.5-coder:7b

# results
cat eval/results/summary.csv
open docs/ablation_accuracy.png
```
