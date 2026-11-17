"""
RAG indexer — builds ChromaDB collections from:
  1. table documents  (schema + sample values per table)
  2. foreign-key relationship documents
  3. business rule documents
  4. few-shot example documents (question -> SQL pairs)

run once:  python rag/indexer.py
"""
import os, sys, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sqlalchemy import create_engine, inspect, text
import config

EMBED_FN = SentenceTransformerEmbeddingFunction(model_name=config.EMBED_MODEL)


def get_client():
    os.makedirs(config.CHROMA_DIR, exist_ok=True)
    return chromadb.PersistentClient(path=config.CHROMA_DIR)


def _sample_values(engine, table, col, n=5):
    try:
        with engine.connect() as conn:
            rows = conn.execute(
                text(f'SELECT DISTINCT "{col}" FROM "{table}" WHERE "{col}" IS NOT NULL LIMIT {n}')
            ).fetchall()
        return [str(r[0]) for r in rows]
    except Exception:
        return []


def index_tables(client, engine):
    """One document per table: description + columns + types + sample values."""
    insp = inspect(engine)
    col = client.get_or_create_collection("tables", embedding_function=EMBED_FN)
    col.delete(where={"type": "table"})

    docs, ids, metas = [], [], []
    for tname in insp.get_table_names():
        columns = insp.get_columns(tname)
        fks = insp.get_foreign_keys(tname)
        fk_info = ", ".join(
            f"{f['constrained_columns']} -> {f['referred_table']}.{f['referred_columns']}"
            for f in fks
        )
        col_lines = []
        for c in columns:
            samples = _sample_values(engine, tname, c["name"])
            sample_str = f"  samples: {', '.join(samples)}" if samples else ""
            col_lines.append(f"  {c['name']} {c['type']}{sample_str}")

        doc = (
            f"Table: {tname}\n"
            f"Columns:\n" + "\n".join(col_lines) +
            (f"\nForeign keys: {fk_info}" if fk_info else "")
        )
        docs.append(doc)
        ids.append(f"table_{tname}")
        metas.append({"type": "table", "table": tname})

    col.add(documents=docs, ids=ids, metadatas=metas)
    print(f"indexed {len(docs)} table documents")
    return col


def index_fk_relationships(client, engine):
    """One document per FK relationship so the retriever can suggest join paths."""
    insp = inspect(engine)
    col = client.get_or_create_collection("fk_relationships", embedding_function=EMBED_FN)
    col.delete(where={"type": "fk"})

    docs, ids, metas = [], [], []
    for tname in insp.get_table_names():
        for fk in insp.get_foreign_keys(tname):
            src_cols = ", ".join(fk["constrained_columns"])
            ref_tbl  = fk["referred_table"]
            ref_cols = ", ".join(fk["referred_columns"])
            doc = (
                f"JOIN path: {tname}.{src_cols} = {ref_tbl}.{ref_cols}. "
                f"To link {tname} with {ref_tbl}, join on "
                f"{tname}.{src_cols} = {ref_tbl}.{ref_cols}."
            )
            fk_id = f"fk_{tname}_{src_cols}_{ref_tbl}"
            docs.append(doc)
            ids.append(fk_id)
            metas.append({"type": "fk", "from": tname, "to": ref_tbl})

    if docs:
        col.add(documents=docs, ids=ids, metadatas=metas)
    print(f"indexed {len(docs)} FK relationship documents")
    return col


def index_rules(client):
    """One document per business rule line."""
    col = client.get_or_create_collection("rules", embedding_function=EMBED_FN)
    col.delete(where={"type": "rule"})

    with open(config.RULES_PATH) as f:
        rules = [l.strip() for l in f if l.strip() and not l.startswith("#")]

    docs, ids, metas = [], [], []
    for i, rule in enumerate(rules):
        docs.append(rule)
        ids.append(f"rule_{i}")
        metas.append({"type": "rule"})

    col.add(documents=docs, ids=ids, metadatas=metas)
    print(f"indexed {len(docs)} rule documents")
    return col


def index_examples(client):
    """Few-shot question->SQL examples for retrieval."""
    col = client.get_or_create_collection("examples", embedding_function=EMBED_FN)
    col.delete(where={"type": "example"})

    with open(config.EXAMPLES_PATH) as f:
        examples = json.load(f)

    docs, ids, metas = [], [], []
    for i, ex in enumerate(examples):
        doc = f"Question: {ex['q']}\nSQL: {ex['sql']}"
        docs.append(doc)
        ids.append(f"example_{i}")
        metas.append({"type": "example", "sql": ex["sql"]})

    col.add(documents=docs, ids=ids, metadatas=metas)
    print(f"indexed {len(docs)} example documents")
    return col


def build_index():
    engine = create_engine(config.DATABASE_URL)
    client = get_client()
    index_tables(client, engine)
    index_fk_relationships(client, engine)
    index_rules(client)
    index_examples(client)
    print("RAG index built successfully.")


if __name__ == "__main__":
    build_index()
