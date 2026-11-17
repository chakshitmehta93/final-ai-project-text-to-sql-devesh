"""
Schema / RAG agent — step 2 of the pipeline.
Input : question string
Output: context string + retrieval trace
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from rag.retriever import get_retriever


def run(question, use_rag=True):
    retriever = get_retriever()
    context, trace = retriever.build_context(question, use_rag=use_rag)
    return {"context": context, "retrieval_trace": trace}
