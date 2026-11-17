"""
Streamlit UI for Agentic Text-to-SQL.
Run: streamlit run app.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, inspect
from dotenv import load_dotenv

load_dotenv(override=True)

import config

st.set_page_config(
    page_title="Agentic Text-to-SQL",
    page_icon=":material/database:",
    layout="wide",
)

# Initialize session state
if "question_input" not in st.session_state:
    st.session_state.question_input = "Show the top 10 students from CSE who scored above 80"
if "last_result" not in st.session_state:
    st.session_state.last_result = None
if "last_question" not in st.session_state:
    st.session_state.last_question = ""


@st.cache_data(ttl=300)
def get_db_summary(db_url):
    try:
        engine = create_engine(db_url)
        insp = inspect(engine)
        tables = {}
        for t in insp.get_table_names():
            cols = [f"{c['name']} ({c['type']})" for c in insp.get_columns(t)]
            tables[t] = cols
        engine.dispose()
        return tables
    except Exception:
        return {}


# ── sidebar settings ──────────────────────────────────────────────────────────
with st.sidebar:
    st.subheader(":material/tune: Pipeline Configuration")

    use_rag = st.toggle("Vector RAG retrieval", value=True, help="Retrieve relevant schema, FK join paths, business rules, and few-shot examples from ChromaDB")
    use_validation = st.toggle("Self-correction validation loop", value=True, help="Validate syntax, schema, SELECT-only guardrails, and EXPLAIN plan (up to 3 retries)")
    use_optimizer = st.toggle("SQL equivalence optimizer", value=True, help="Optimize SQL via sqlglot and verify row-level equivalence")

    st.divider()
    st.subheader(":material/psychology: LLM Engine")

    backend_labels = {
        "colab": "Colab GPU API (Qwen 1.5B LoRA)",
        "smart_local": "Instant Local Engine (Zero-Setup)",
        "ollama": "Ollama Local Server",
        "huggingface": "HuggingFace Transformers (Local)",
    }
    backends = list(backend_labels.keys())
    default_idx = backends.index(config.LLM_BACKEND) if config.LLM_BACKEND in backends else 0

    selected_backend = st.selectbox(
        "Active backend",
        backends,
        index=default_idx,
        format_func=lambda k: backend_labels[k],
    )
    config.LLM_BACKEND = selected_backend

    if selected_backend == "colab":
        colab_url = st.text_input(
            "Colab ngrok URL",
            value=config.COLAB_API_URL,
            placeholder="https://xxxx.ngrok-free.dev",
        )
        colab_token = st.text_input(
            "Colab API Token",
            value=config.COLAB_API_TOKEN,
            type="password",
        )
        auto_fb = st.toggle(
            "Auto-fallback if Colab tunnel is offline",
            value=getattr(config, "AUTO_FALLBACK", True),
            help="Automatically switch to the Instant Local Engine if the Colab ngrok tunnel is offline or times out.",
        )
        config.COLAB_API_URL = colab_url.strip().rstrip("/")
        config.COLAB_API_TOKEN = colab_token.strip()
        config.AUTO_FALLBACK = auto_fb

        from core.llm import ColabBackend
        cb = ColabBackend(base_url=config.COLAB_API_URL or "http://localhost", api_token=config.COLAB_API_TOKEN or "x")
        if config.COLAB_API_URL and cb.is_available():
            st.badge("Colab Tunnel Online", icon=":material/check_circle:", color="green")
        elif auto_fb:
            st.badge("Colab Offline — Auto-Fallback Ready", icon=":material/bolt:", color="orange")
        else:
            st.badge("Colab Tunnel Offline", icon=":material/error:", color="red")

    elif selected_backend == "smart_local":
        st.badge("Instant Local Mode (<50ms)", icon=":material/bolt:", color="green")
        st.caption("Uses ChromaDB vector RAG + compositional SQL synthesis. Works offline with zero GPU setup.")

    elif selected_backend == "ollama":
        model_name = st.text_input("Ollama model", value=config.OLLAMA_MODEL)
        config.OLLAMA_MODEL = model_name.strip()
        auto_fb = st.toggle("Auto-fallback if Ollama is offline", value=getattr(config, "AUTO_FALLBACK", True))
        config.AUTO_FALLBACK = auto_fb

    elif selected_backend == "huggingface":
        hf_models = [
            "Qwen/Qwen2.5-Coder-1.5B-Instruct",
            "Qwen/Qwen2.5-Coder-3B-Instruct",
            "Qwen/Qwen2.5-Coder-7B-Instruct",
        ]
        hf_idx = hf_models.index(config.HF_MODEL) if config.HF_MODEL in hf_models else 0
        chosen_hf = st.selectbox("HuggingFace model", hf_models, index=hf_idx)
        config.HF_MODEL = chosen_hf
        st.caption(f"Model path: `{config.best_hf_model()}`")

    st.divider()
    st.subheader(":material/database: Database")
    db_url = st.text_input("Database URL", value=config.DATABASE_URL)
    config.DATABASE_URL = db_url.strip()
    if "sqlite" in config.DATABASE_URL:
        config.DB_PATH = config.DATABASE_URL.replace("sqlite:///", "")

    schema_map = get_db_summary(config.DATABASE_URL)
    if schema_map:
        with st.expander(f":material/schema: Schema Browser ({len(schema_map)} tables)", expanded=False):
            for tname, cols in sorted(schema_map.items()):
                st.markdown(f"**`{tname}`** ({len(cols)} cols)")
                st.caption(", ".join(cols))

# ── header ────────────────────────────────────────────────────────────────────
col_title, col_badges = st.columns([3, 2], vertical_alignment="bottom")
with col_title:
    st.title(":material/database: Agentic Text-to-SQL")
    st.caption(
        "9-agent Text-to-SQL pipeline with ChromaDB vector RAG, sqlglot AST validation, "
        "self-correction loop, equivalence-checked optimization, and visual analytics."
    )
with col_badges:
    with st.container(horizontal=True):
        st.badge(f"Backend: {config.LLM_BACKEND.upper()}", icon=":material/memory:", color="blue")
        st.badge("RAG: ON" if use_rag else "RAG: OFF", icon=":material/search:", color="green" if use_rag else "gray")
        st.badge("Validator: ON" if use_validation else "Validator: OFF", icon=":material/verified:", color="green" if use_validation else "gray")
        st.badge("12 Tables · 300 Students", icon=":material/table_chart:", color="violet")

# ── query bar & quick examples ────────────────────────────────────────────────
with st.container(border=True):
    st.markdown("**:material/chat: Ask a question in plain English**")

    preset_questions = [
        "Show the top 10 students from CSE who scored above 80",
        "Which departments have more than 20 students?",
        "Show students with low attendance",
        "List all fee defaulters",
        "Average score per department",
        "Count of students per hostel",
        "Show all club members and their clubs",
        "Top 3 courses by average score",
    ]

    selected_pill = st.pills(
        "Sample queries",
        preset_questions,
        selection_mode="single",
        label_visibility="collapsed",
        key="sample_pill",
    )

    if selected_pill and selected_pill != st.session_state.get("_prev_pill"):
        st.session_state._prev_pill = selected_pill
        st.session_state.question_input = selected_pill

    q_col, btn_col = st.columns([5, 1], vertical_alignment="bottom")
    with q_col:
        question = st.text_input(
            "Question",
            key="question_input",
            placeholder="e.g. Show the top 10 students from CSE who scored above 80",
            label_visibility="collapsed",
        )
    with btn_col:
        run_btn = st.button(":material/play_arrow: Run Query", type="primary", width="stretch")

# Automatically execute on first load or when Run is clicked
should_run = run_btn or (st.session_state.last_result is None and bool(question.strip()))

if should_run and question.strip():
    try:
        with st.spinner("Running 9-agent Text-to-SQL pipeline…"):
            from core.pipeline import run as pipeline_run
            result = pipeline_run(
                question.strip(),
                use_rag=use_rag,
                use_validation=use_validation,
                use_optimizer=use_optimizer,
            )
            st.session_state.last_result = result
            st.session_state.last_question = question.strip()
    except Exception as e:
        st.error(f"Pipeline execution failed: {str(e)}")
        st.exception(e)
        st.stop()

result = st.session_state.last_result
if not result:
    st.stop()

# ── KPI summary metrics ───────────────────────────────────────────────────────
total_latency = sum(step.get("time_s", 0) for step in result.get("trace", []))
rows = result.get("rows", [])
columns = result.get("columns", [])
attempts = result.get("attempts", 1)
has_error = bool(result.get("error"))

m1, m2, m3, m4 = st.columns(4)
with m1:
    with st.container(border=True):
        st.metric(
            "Pipeline Status",
            "Failed" if has_error else "Verified ✓",
            delta="Error" if has_error else f"{len(result.get('trace', []))} steps completed",
            delta_color="inverse" if has_error else "normal",
        )
with m2:
    with st.container(border=True):
        st.metric(
            "Rows Returned",
            f"{len(rows):,}",
            delta=f"{len(columns)} columns",
            delta_color="off",
        )
with m3:
    with st.container(border=True):
        st.metric(
            "Validation Attempts",
            f"{attempts} / {config.MAX_RETRIES}",
            delta="First-pass valid" if attempts == 1 else f"Self-corrected ({attempts} tries)",
            delta_color="normal" if attempts == 1 else "off",
        )
with m4:
    with st.container(border=True):
        st.metric(
            "Total Latency",
            f"{total_latency:.2f} s",
            delta=f"{int(total_latency * 1000)} ms end-to-end",
            delta_color="off",
        )

if has_error:
    st.error(result["error"], title="Query Execution Error", icon=":material/error:")

# ── main result workspace (SQL + Insights | Table + Chart) ───────────────────
left_col, right_col = st.columns([5, 7])

with left_col:
    with st.container(border=True):
        st.subheader(":material/code: Generated SQL")
        sql_to_show = result.get("optimized_sql") or result.get("sql", "")
        st.code(sql_to_show, language="sql")

        if result.get("optimized_sql"):
            st.badge("Optimized by sqlglot", icon=":material/tune:", color="green")
            with st.expander("View unoptimized SQL"):
                st.code(result.get("sql", ""), language="sql")
        else:
            st.badge("Equivalence-checked SQL", icon=":material/verified:", color="blue")

    explanation = result.get("explanation", "")
    insights = result.get("insights", [])
    if explanation or insights:
        with st.container(border=True):
            st.subheader(":material/lightbulb: Explanation & Key Insights")
            if explanation:
                st.write(explanation)
            if insights:
                st.markdown("**Key Findings:**")
                for ins in insights:
                    st.markdown(f"- {ins}")

with right_col:
    with st.container(border=True):
        tab_table, tab_chart = st.tabs([
            f":material/table_rows: Data Table ({len(rows)} rows)",
            ":material/bar_chart: Visual Chart",
        ])

        with tab_table:
            if rows:
                df = pd.DataFrame(rows, columns=columns)
                st.dataframe(df, alt="Query results table", height=360)
                csv_bytes = df.to_csv(index=False).encode("utf-8")
                st.download_button(
                    ":material/download: Download CSV",
                    data=csv_bytes,
                    file_name="query_results.csv",
                    mime="text/csv",
                )
            elif not has_error:
                st.info("Query executed successfully but returned 0 rows.")

        with tab_chart:
            chart = result.get("chart")
            if chart:
                st.plotly_chart(chart, alt="Query result visualization")
            else:
                st.info("No automatic chart applicable for this result shape.")

# ── 9-step pipeline trace ─────────────────────────────────────────────────────
st.subheader(":material/account_tree: Multi-Agent Pipeline Trace")
st.caption("Inspect the exact input, output, and execution time of every agent in the workflow.")

STEP_ICONS = {
    "schema_rag": ":material/search:",
    "sql_generation": ":material/code:",
    "sql_validation": ":material/verified:",
    "sql_optimization": ":material/tune:",
    "execution": ":material/play_circle:",
    "result_processing": ":material/table_chart:",
    "explanation": ":material/lightbulb:",
}

for idx, entry in enumerate(result.get("trace", []), start=1):
    name = entry["step"]
    icon = STEP_ICONS.get(name, ":material/circle:")
    t_ms = int(entry.get("time_s", 0) * 1000)
    label = f"{icon} **Step {idx}: {name.replace('_', ' ').title()}** — `{t_ms} ms`"

    with st.expander(label, expanded=False):
        out = entry.get("output", {})
        if name == "schema_rag":
            rt = out.get("retrieval_trace", {})
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Business Rules Retrieved:**")
                for r in rt.get("rules", []):
                    st.markdown(f"- {r}")
                if not rt.get("rules"):
                    st.caption("None (RAG disabled)")
            with c2:
                st.markdown("**Few-Shot Examples Retrieved:**")
                for e in rt.get("examples", []):
                    st.code(e, language="sql")
                if not rt.get("examples"):
                    st.caption("None (RAG disabled)")
            with st.expander("View Full Prompt Schema Context"):
                st.code(rt.get("schema", out.get("context", "")), language="sql")

        elif name == "sql_generation":
            st.markdown("**Generated SQL:**")
            st.code(out.get("sql", ""), language="sql")
            with st.expander("View Full LLM Prompt"):
                st.text(out.get("prompt", ""))

        elif name == "sql_validation":
            if out.get("valid"):
                st.success("AST Syntax Check, Schema Check, Foreign-Key Check & EXPLAIN Dry-Run Passed ✓", icon=":material/check_circle:")
            else:
                st.error(f"Validation Failed: {out.get('error')}", icon=":material/error:")

        elif name == "sql_optimization":
            st.markdown(f"**Rewritten:** `{out.get('changed')}` — *{out.get('reason', '')}*")
            if out.get("changed"):
                st.code(out.get("optimized_sql", ""), language="sql")

        elif name == "execution":
            st.markdown(f"**Rows Fetched:** `{out.get('row_count', 0)}` (Read-Only mode, timeout={config.QUERY_TIMEOUT}s)")
            if out.get("error"):
                st.error(out["error"])

        elif name == "result_processing":
            st.markdown(f"**Numeric Columns:** `{out.get('num_cols', [])}` | **Categorical Columns:** `{out.get('cat_cols', [])}`")
            if out.get("stats"):
                st.json(out["stats"])

        elif name == "explanation":
            st.write(out.get("explanation", ""))
            for ins in out.get("insights", []):
                st.markdown(f"- {ins}")
        else:
            st.json(out)
