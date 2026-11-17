"""
RAG retriever — queries ChromaDB collections and builds schema context.
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from sqlalchemy import create_engine, inspect
import config

EMBED_FN = SentenceTransformerEmbeddingFunction(model_name=config.EMBED_MODEL)


class Retriever:
    def __init__(self):
        self.client = chromadb.PersistentClient(path=config.CHROMA_DIR)
        self._cols = {}

    def _col(self, name):
        if name not in self._cols:
            self._cols[name] = self.client.get_collection(name, embedding_function=EMBED_FN)
        return self._cols[name]

    def retrieve_tables(self, question, k=None):
        k = k or config.RAG_TOP_K
        res = self._col("tables").query(query_texts=[question], n_results=k)
        return res["documents"][0], res["metadatas"][0]

    def retrieve_fk(self, question, k=None):
        k = k or config.RAG_TOP_K
        try:
            res = self._col("fk_relationships").query(query_texts=[question], n_results=k)
            return res["documents"][0]
        except Exception:
            return []

    def retrieve_rules(self, question, k=None):
        k = k or config.RAG_TOP_K
        res = self._col("rules").query(query_texts=[question], n_results=k)
        return res["documents"][0]

    def retrieve_examples(self, question, k=None):
        k = k or config.RAG_TOP_K
        res = self._col("examples").query(query_texts=[question], n_results=k)
        return res["documents"][0]

    def build_context(self, question, use_rag=True):
        """
        Returns (context_string, trace_dict).
        trace_dict contains what was retrieved for transparency.
        """
        engine = create_engine(config.DATABASE_URL)
        insp   = inspect(engine)

        # always include full schema (small DB; for large DBs swap to retrieved-only)
        schema_lines = []
        for tname in insp.get_table_names():
            cols = insp.get_columns(tname)
            fks  = insp.get_foreign_keys(tname)
            col_defs = ", ".join(f"{c['name']} ({c['type']})" for c in cols)
            fk_defs  = ""
            if fks:
                fk_defs = " | FK: " + ", ".join(
                    f"{f['constrained_columns']} -> {f['referred_table']}.{f['referred_columns']}"
                    for f in fks
                )
            schema_lines.append(f"  {tname}({col_defs}){fk_defs}")

        schema_str = "Database schema:\n" + "\n".join(schema_lines)

        trace = {"schema": schema_str, "rules": [], "fk": [], "examples": []}

        if not use_rag:
            return schema_str, trace

        # retrieve relevant rules
        rules = self.retrieve_rules(question)
        trace["rules"] = rules

        # retrieve FK join hints
        fk_docs = self.retrieve_fk(question)
        trace["fk"] = fk_docs

        # retrieve few-shot examples
        examples = self.retrieve_examples(question)
        trace["examples"] = examples

        parts = [schema_str]
        if rules:
            parts.append("\nRelevant business rules:\n" + "\n".join(f"- {r}" for r in rules))
        if fk_docs:
            parts.append("\nJoin hints:\n" + "\n".join(f"- {d}" for d in fk_docs))
        if examples:
            parts.append("\nSimilar solved examples:\n" + "\n".join(examples))

        return "\n".join(parts), trace


# module-level singleton
_retriever = None

def get_retriever():
    global _retriever
    if _retriever is None:
        _retriever = Retriever()
    return _retriever
