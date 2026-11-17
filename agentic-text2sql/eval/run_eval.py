"""
eval/run_eval.py — evaluate the pipeline on eval_set.json
Runs 5 systems (A-E) and saves per-question logs + summary CSV.

Usage:
    python eval/run_eval.py --system E --model qwen2.5-coder:7b
    python eval/run_eval.py --all
"""
import sys, os, json, csv, time, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config

SYSTEMS = {
    "A": dict(use_rag=False, use_validation=False, use_optimizer=False),
    "B": dict(use_rag=True,  use_validation=False, use_optimizer=False),
    "C": dict(use_rag=False, use_validation=True,  use_optimizer=False),
    "D": dict(use_rag=True,  use_validation=True,  use_optimizer=False),
    "E": dict(use_rag=True,  use_validation=True,  use_optimizer=True),
}


def norm_rows(rows):
    """Order-insensitive normalised row set for comparison."""
    def norm_val(v):
        try:
            return round(float(v), 4)
        except (TypeError, ValueError):
            return str(v).strip().lower()
    return set(tuple(norm_val(c) for c in row) for row in rows)


def run_one(question, gold_sql, settings):
    from core.pipeline import run as pipeline_run
    from agents.executor_agent import run as exec_sql

    t0 = time.time()
    result = pipeline_run(question, **settings)
    latency = round(time.time() - t0, 2)

    # execute gold to get expected rows
    gold_res = exec_sql(gold_sql)
    gold_rows = gold_res.get("rows", [])

    pred_rows = result.get("rows", [])

    exact_match = norm_rows(pred_rows) == norm_rows(gold_rows)
    valid = result.get("error") is None and bool(result.get("sql"))

    return {
        "question":    question,
        "gold_sql":    gold_sql,
        "pred_sql":    result.get("sql", ""),
        "valid":       valid,
        "exact_match": exact_match,
        "attempts":    result.get("attempts", 1),
        "latency_s":   latency,
        "error":       result.get("error", ""),
    }


def run_system(system_id, eval_set, model, results_dir):
    settings = SYSTEMS[system_id]
    config.OLLAMA_MODEL = model

    os.makedirs(results_dir, exist_ok=True)
    summary = []

    for i, item in enumerate(eval_set):
        q     = item["q"]
        gold  = item["sql"]
        level = item.get("level", "unknown")
        print(f"[{system_id}] {i+1}/{len(eval_set)} {level}: {q[:60]}...")

        try:
            res = run_one(q, gold, settings)
        except Exception as e:
            res = {"question": q, "gold_sql": gold, "pred_sql": "",
                   "valid": False, "exact_match": False,
                   "attempts": 0, "latency_s": 0, "error": str(e)}

        res["level"] = level
        res["system"] = system_id

        # save per-question json
        fname = f"{results_dir}/sys{system_id}_{i:03d}.json"
        with open(fname, "w") as f:
            json.dump(res, f, indent=2)

        summary.append(res)
        print(f"   match={res['exact_match']} valid={res['valid']} {res['latency_s']}s")

    return summary


def print_summary(system_id, rows):
    total    = len(rows)
    em       = sum(r["exact_match"] for r in rows)
    valid    = sum(r["valid"] for r in rows)
    avg_lat  = sum(r["latency_s"] for r in rows) / max(total, 1)
    avg_att  = sum(r["attempts"] for r in rows) / max(total, 1)

    print(f"\n── System {system_id} ─────────────────────────")
    print(f"  Accuracy (exec match): {em}/{total} = {em/total*100:.1f}%")
    print(f"  Validity rate:         {valid/total*100:.1f}%")
    print(f"  Avg attempts:          {avg_att:.2f}")
    print(f"  Avg latency:           {avg_lat:.2f}s")
    for level in ["easy", "medium", "hard"]:
        sub = [r for r in rows if r["level"] == level]
        if sub:
            acc = sum(r["exact_match"] for r in sub) / len(sub) * 100
            print(f"  {level:8s} accuracy: {acc:.1f}%  ({len(sub)} questions)")


def save_csv(all_rows, path="eval/results/summary.csv"):
    if not all_rows:
        return
    keys = list(all_rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(all_rows)
    print(f"\nSummary saved to {path}")


def make_charts(all_summary):
    """Generate bar charts and save to docs/."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib
        matplotlib.use("Agg")

        systems = sorted(set(r["system"] for r in all_summary))
        accuracy = []
        for s in systems:
            rows = [r for r in all_summary if r["system"] == s]
            acc  = sum(r["exact_match"] for r in rows) / len(rows) * 100
            accuracy.append(acc)

        os.makedirs("docs", exist_ok=True)

        fig, ax = plt.subplots(figsize=(8, 4))
        ax.bar(systems, accuracy, color="steelblue")
        ax.set_xlabel("System")
        ax.set_ylabel("Execution Accuracy (%)")
        ax.set_title("Ablation: Execution Accuracy by System")
        ax.set_ylim(0, 100)
        for i, v in enumerate(accuracy):
            ax.text(i, v + 1, f"{v:.1f}%", ha="center")
        plt.tight_layout()
        plt.savefig("docs/ablation_accuracy.png")
        print("Chart saved to docs/ablation_accuracy.png")

    except Exception as e:
        print(f"Chart generation failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--system", default="E", help="A/B/C/D/E or 'all'")
    parser.add_argument("--model",  default=config.OLLAMA_MODEL)
    parser.add_argument("--all",    action="store_true")
    args = parser.parse_args()

    with open("data/eval_set.json") as f:
        eval_set = json.load(f)

    to_run = list(SYSTEMS.keys()) if args.all or args.system == "all" else [args.system.upper()]

    all_rows = []
    for sys_id in to_run:
        rows = run_system(sys_id, eval_set, args.model, "eval/results")
        print_summary(sys_id, rows)
        all_rows.extend(rows)

    save_csv(all_rows)
    if len(to_run) > 1:
        make_charts(all_rows)
