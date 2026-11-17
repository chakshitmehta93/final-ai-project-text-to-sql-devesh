"""
SQL generation agent — step 3 of the pipeline.
Input : question, context, optional previous error + SQL
Output: generated SQL string
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.llm import get_llm
from core.prompts import sql_generation_prompt


def run(question, context, error=None, prev_sql=None):
    llm    = get_llm()
    prompt = sql_generation_prompt(question, context, error, prev_sql)
    raw    = llm.generate(prompt, max_tokens=512)
    sql    = llm.extract_sql(raw)
    return {"sql": sql, "prompt": prompt, "raw_output": raw}
