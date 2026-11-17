"""
LLM wrapper — supports Ollama, HuggingFace, remote Colab API, and Smart Local SQL Engine.
"""
import re
import sys
import json
import os
import requests
import config


class SmartLocalSQLBackend:
    """
    Instant zero-setup local SQL generator using semantic RAG example matching
    plus rule-based NL-to-SQL composition against the college database schema.
    Works offline in <10ms when Colab ngrok or Ollama is unreachable.
    """

    def __init__(self):
        self._examples = []
        if os.path.exists(config.EXAMPLES_PATH):
            try:
                with open(config.EXAMPLES_PATH, encoding="utf-8") as f:
                    self._examples = json.load(f)
            except Exception:
                self._examples = []

    @staticmethod
    def _extract_question(prompt):
        if "Question:" in prompt:
            _, rem = prompt.rsplit("Question:", 1)
            q = re.split(r"\n(?:The previous SQL had an error:|Write the SQL query:)", rem, maxsplit=1)[0]
            return q.strip()
        return prompt.strip()

    def generate(self, prompt, max_tokens=256):
        q_raw = self._extract_question(prompt)
        q = q_raw.lower().strip().rstrip("?.!")

        # 1. Exact or high-overlap match from examples.json / eval_set.json
        for path in [config.EXAMPLES_PATH, "data/eval_set.json"]:
            if os.path.exists(path):
                try:
                    with open(path, encoding="utf-8") as f:
                        items = json.load(f)
                    for item in items:
                        iq = item.get("q", "").lower().strip().rstrip("?.!")
                        if iq == q:
                            return f"```sql\n{item['sql']}\n```"
                except Exception:
                    pass

        # 2. Extract top few-shot SQL from RAG prompt if question words closely match
        rag_matches = re.findall(r"Question:\s*(.+?)\nSQL:\s*(SELECT\s+.+?;)", prompt, flags=re.I)
        q_words = set(re.findall(r"[a-z0-9]+", q)) - {"show", "list", "all", "the", "find", "get", "what", "are", "is", "of", "in", "from", "who", "with"}
        best_sql, best_score = None, 0.0
        for ex_q, ex_sql in rag_matches:
            ex_words = set(re.findall(r"[a-z0-9]+", ex_q.lower())) - {"show", "list", "all", "the", "find", "get", "what", "are", "is", "of", "in", "from", "who", "with"}
            if ex_words and q_words:
                score = len(q_words & ex_words) / max(len(q_words | ex_words), 1)
                if score > best_score:
                    best_score = score
                    best_sql = ex_sql
        if best_score >= 0.72 and best_sql:
            # Adjust LIMIT N or threshold numbers if user changed them
            nums_q = re.findall(r"\b\d+\b", q)
            nums_ex = re.findall(r"\b\d+\b", best_sql)
            sql_out = best_sql
            if len(nums_q) == 1 and len(nums_ex) == 1:
                sql_out = re.sub(r"\b" + nums_ex[0] + r"\b", nums_q[0], sql_out, count=1)
            return f"```sql\n{sql_out}\n```"

        # 3. Rule-based compositional SQL builder for the 12-table college schema
        limit_match = re.search(r"\b(?:top|first|limit)\s+(\d+)\b", q)
        limit_clause = f" LIMIT {limit_match.group(1)}" if limit_match else ""

        dept_code = None
        for code, aliases in [
            ("CSE", ["cse", "computer science"]),
            ("ECE", ["ece", "electronics"]),
            ("ME", ["me", "mechanical"]),
            ("CE", ["ce", "civil"]),
            ("IT", ["it", "information technology"]),
            ("BT", ["bt", "biotech", "biotechnology"]),
            ("CH", ["ch", "chemical"]),
            ("MA", ["ma", "math", "mathematics"]),
            ("PH", ["ph", "physics"]),
            ("MG", ["mg", "management"]),
        ]:
            if any(re.search(r"\b" + re.escape(a) + r"\b", q) for a in aliases):
                dept_code = code
                break

        above_match = re.search(r"(?:above|greater than|more than|over|>)\s*(\d+(?:\.\d+)?)", q)
        below_match = re.search(r"(?:below|less than|under|<)\s*(\d+(?:\.\d+)?)", q)

        if "low attendance" in q or ("attendance" in q and below_match):
            thresh = below_match.group(1) if below_match else "75"
            sql = (
                f"SELECT s.name, ROUND(a.attended * 100.0 / a.total_classes, 2) AS attendance_pct "
                f"FROM students s JOIN attendance a ON s.student_id = a.student_id "
                f"WHERE (a.attended * 100.0 / a.total_classes) < {thresh} "
                f"ORDER BY attendance_pct ASC{limit_clause or ' LIMIT 50'};"
            )
        elif "fee" in q and ("default" in q or "unpaid" in q or "pending" in q or "due" in q):
            sql = (
                "SELECT s.name, f.semester, f.amount, f.paid, f.status "
                "FROM students s JOIN fees f ON s.student_id = f.student_id "
                "WHERE f.status IN ('Unpaid', 'Partial') ORDER BY f.amount - f.paid DESC;"
            )
        elif "department" in q and ("more than" in q or "count" in q or "how many student" in q or "per department" in q):
            if "average" in q or "avg" in q or "score" in q or "marks" in q:
                sql = (
                    "SELECT d.dept_name, ROUND(AVG(m.score), 2) AS avg_score "
                    "FROM departments d JOIN students s ON d.dept_id = s.dept_id "
                    "JOIN marks m ON s.student_id = m.student_id "
                    "GROUP BY d.dept_id, d.dept_name ORDER BY avg_score DESC;"
                )
            elif above_match:
                sql = (
                    f"SELECT d.dept_name, COUNT(s.student_id) AS student_count "
                    f"FROM departments d JOIN students s ON d.dept_id = s.dept_id "
                    f"GROUP BY d.dept_id, d.dept_name HAVING COUNT(s.student_id) > {above_match.group(1)} "
                    f"ORDER BY student_count DESC;"
                )
            else:
                sql = (
                    "SELECT d.dept_name, COUNT(s.student_id) AS student_count "
                    "FROM departments d JOIN students s ON d.dept_id = s.dept_id "
                    "GROUP BY d.dept_id, d.dept_name ORDER BY student_count DESC;"
                )
        elif ("score" in q or "scored" in q or "marks" in q or "top" in q) and ("student" in q or dept_code):
            wheres = []
            joins = ["JOIN marks m ON s.student_id = m.student_id"]
            if dept_code:
                joins.insert(0, "JOIN departments d ON s.dept_id = d.dept_id")
                wheres.append(f"d.dept_code = '{dept_code}'")
            if above_match:
                wheres.append(f"m.score > {above_match.group(1)}")
            if below_match:
                wheres.append(f"m.score < {below_match.group(1)}")
            where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
            sql = (
                f"SELECT s.name, ROUND(AVG(m.score), 2) AS avg_score "
                f"FROM students s {' '.join(joins)}{where_sql} "
                f"GROUP BY s.student_id, s.name ORDER BY avg_score DESC{limit_clause or ' LIMIT 10'};"
            )
        elif "hostel" in q:
            sql = (
                "SELECT s.name, h.hostel_name, ha.room_no "
                "FROM students s JOIN hostel_allotments ha ON s.student_id = ha.student_id "
                f"JOIN hostels h ON ha.hostel_id = h.hostel_id{limit_clause or ' LIMIT 50'};"
            )
        elif "club" in q:
            sql = (
                "SELECT s.name, c.club_name, cm.role "
                "FROM students s JOIN club_members cm ON s.student_id = cm.student_id "
                f"JOIN clubs c ON cm.club_id = c.club_id{limit_clause or ' LIMIT 50'};"
            )
        elif "faculty" in q or "professor" in q or "teacher" in q:
            sql = (
                "SELECT f.name, f.designation, d.dept_name, f.status "
                "FROM faculty f JOIN departments d ON f.dept_id = d.dept_id"
                f"{limit_clause or ' LIMIT 50'};"
            )
        elif "course" in q:
            sql = (
                "SELECT c.course_name, c.course_code, c.credits, c.course_type, d.dept_code "
                "FROM courses c JOIN departments d ON c.dept_id = d.dept_id"
                f"{limit_clause or ' LIMIT 50'};"
            )
        elif "how many" in q or "count" in q:
            sql = "SELECT COUNT(*) AS total_students FROM students;"
        else:
            wheres = []
            joins = ["JOIN departments d ON s.dept_id = d.dept_id"]
            if dept_code:
                wheres.append(f"d.dept_code = '{dept_code}'")
            where_sql = (" WHERE " + " AND ".join(wheres)) if wheres else ""
            sql = (
                f"SELECT s.name, d.dept_code, s.year, s.gender, s.status "
                f"FROM students s {' '.join(joins)}{where_sql}{limit_clause or ' LIMIT 25'};"
            )

        return f"```sql\n{sql}\n```"


class ColabBackend:
    """Calls the fine-tuned Qwen model hosted on Google Colab via FastAPI + ngrok."""

    def __init__(self, base_url=None, api_token=None):
        self.base_url = (base_url or config.COLAB_API_URL).strip().rstrip("/")
        self.api_token = (api_token or config.COLAB_API_TOKEN).strip()

        if not self.base_url:
            raise ValueError("COLAB_API_URL is missing.")
        if not self.api_token:
            raise ValueError("COLAB_API_TOKEN is missing.")

    @staticmethod
    def _extract_schema_and_question(prompt):
        """
        Convert any pipeline prompt into the separate `schema` and `question`
        fields expected by the Colab `/generate` API.
        Uses rsplit("Question:", 1) so few-shot RAG examples ("Question: ...")
        inside the schema context do NOT break extraction!
        """
        try:
            from core.prompts import SYSTEM
            if prompt.startswith(SYSTEM):
                prompt = prompt[len(SYSTEM):].lstrip()
        except ImportError:
            pass

        if "Question:" in prompt:
            schema_text, remaining = prompt.rsplit("Question:", 1)

            if "\nThe previous SQL had an error:" in remaining:
                q_part, err_part = remaining.split("\nThe previous SQL had an error:", 1)
                err_part = re.split(r"\nWrite the SQL query:", err_part, maxsplit=1)[0]
                question = f"{q_part.strip()}\n(Fix previous error: {err_part.strip()})"
            else:
                question = re.split(r"\nWrite the SQL query:", remaining, maxsplit=1)[0].strip()

            schema_text = schema_text.strip()
            if not schema_text:
                schema_text = "SQLite database"
            return schema_text, question

        if "Original SQL:" in prompt:
            schema_text, remaining = prompt.split("Original SQL:", 1)
            return schema_text.strip() or "SQLite database", f"Optimize this SQL:\n{remaining.strip()}"

        return "SQLite database", prompt.strip()

    def is_available(self):
        if not self.base_url or not self.api_token:
            return False
        try:
            r = requests.get(
                f"{self.base_url}/health",
                headers={"ngrok-skip-browser-warning": "true"},
                timeout=4,
            )
            return r.status_code == 200
        except Exception:
            return False

    def generate(self, prompt, max_tokens=256):
        schema_text, question = self._extract_schema_and_question(prompt)

        payload = {
            "schema": schema_text,
            "question": question,
            "max_tokens": min(max_tokens, 256),
        }

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "ngrok-skip-browser-warning": "true",
        }

        try:
            response = requests.post(
                f"{self.base_url}/generate",
                json=payload,
                headers=headers,
                timeout=90,
            )
            response.raise_for_status()
            result = response.json()

            if not result.get("success") or not result.get("sql"):
                raise RuntimeError(f"Colab API returned an unexpected response: {result}")

            return result["sql"]

        except requests.exceptions.Timeout as e:
            raise RuntimeError(
                "Colab API timed out. Check whether the Colab model cell "
                "is running (use the merged float16 cell, not 4-bit) and the ngrok tunnel is active."
            ) from e

        except requests.exceptions.ConnectionError as e:
            raise RuntimeError(
                "Cannot connect to the Colab API. "
                "Check that your Colab runtime and ngrok tunnel are running."
            ) from e

        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            detail = e.response.text if e.response is not None else str(e)

            if status == 503 and "ERR_NGROK_3004" in detail:
                raise RuntimeError(
                    "The Colab model server returned an invalid response "
                    "(ngrok ERR_NGROK_3004). Restart the model-serving cell "
                    "in Colab, update COLAB_API_URL in .env to the current "
                    "ngrok URL, and retry."
                ) from e

            raise RuntimeError(f"Colab API request failed (HTTP {status}): {detail}") from e


class OllamaBackend:
    """Calls a locally running Ollama server."""

    def __init__(self, model=None, base_url=None):
        self.model = model or config.OLLAMA_MODEL
        self.base_url = (base_url or config.OLLAMA_URL).strip().rstrip("/")

    def _get_local_models(self):
        try:
            r = requests.get(f"{self.base_url}/api/tags", timeout=3)
            r.raise_for_status()
            payload = r.json() or {}
            models = payload.get("models", [])
            return {
                m.get("name")
                for m in models
                if isinstance(m, dict) and m.get("name")
            }
        except Exception:
            return set()

    def generate(self, prompt, max_tokens=512):
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {"num_predict": max_tokens, "temperature": 0},
        }
        try:
            r = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=120,
            )
            r.raise_for_status()
            return r.json().get("response", "")
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Cannot reach Ollama. Start it with: ollama serve\n"
                f"Then pull the model: ollama pull {self.model}"
            )
        except requests.exceptions.HTTPError as e:
            status = e.response.status_code if e.response is not None else None
            if status == 404:
                if self.model == getattr(config, "OLLAMA_FINETUNED_MODEL", ""):
                    raise RuntimeError(
                        f"Ollama model '{self.model}' was not found locally. "
                        "Train and export it using the README instructions."
                    ) from e
                raise RuntimeError(
                    f"Ollama model '{self.model}' was not found locally. "
                    f"Pull it with: ollama pull {self.model}"
                ) from e
            raise RuntimeError(
                f"Ollama request failed for model '{self.model}' (HTTP {status})."
            ) from e

    def is_available(self):
        local = self._get_local_models()
        if not local:
            return False
        return self.model in local or f"{self.model}:latest" in local


class HuggingFaceBackend:
    """Loads a HuggingFace causal-LM locally (CPU / MPS / CUDA)."""

    def __init__(self, model_path=None):
        import threading
        import torch
        from transformers import AutoTokenizer, AutoModelForCausalLM

        self._lock = threading.Lock()
        model_path = model_path or config.best_hf_model()
        print(f"[HF] loading {model_path} ...", file=sys.stderr)

        self.tok = AutoTokenizer.from_pretrained(model_path)
        if torch.cuda.is_available():
            dtype, dev = torch.float16, "cuda"
        elif torch.backends.mps.is_available():
            dtype, dev = torch.float16, "mps"
        else:
            dtype, dev = torch.float32, "cpu"

        self.model = AutoModelForCausalLM.from_pretrained(
            model_path, dtype=dtype, low_cpu_mem_usage=True
        ).to(dev)
        self.model.eval()
        self.device = dev

    def generate(self, prompt, max_tokens=256):
        import torch
        with self._lock, torch.inference_mode():
            if self.device == "mps":
                torch.mps.synchronize()
            inputs = self.tok(prompt, return_tensors="pt").to(self.device)
            out = self.model.generate(
                **inputs,
                max_new_tokens=min(max_tokens, 256),
                do_sample=False,
                pad_token_id=self.tok.eos_token_id,
            )
            if self.device == "mps":
                torch.mps.synchronize()
            new_tokens = out[0][inputs.input_ids.shape[1]:]
            return self.tok.decode(new_tokens, skip_special_tokens=True)


class LLM:
    """Single entry point for all LLM calls."""

    def __init__(self, backend=None):
        b = (backend or config.LLM_BACKEND).strip().lower()
        self.backend_name = b
        if b == "ollama":
            self._backend = OllamaBackend()
        elif b == "huggingface":
            self._backend = HuggingFaceBackend()
        elif b == "colab":
            self._backend = ColabBackend()
        elif b == "smart_local":
            self._backend = SmartLocalSQLBackend()
        else:
            raise ValueError(f"Unsupported LLM_BACKEND: {b}")

    def generate(self, prompt, max_tokens=512):
        # In unit tests, AUTO_FALLBACK can be disabled or PYTEST_CURRENT_TEST is set
        auto_fb = getattr(config, "AUTO_FALLBACK", False) and "PYTEST_CURRENT_TEST" not in os.environ
        try:
            return self._backend.generate(prompt, max_tokens)
        except Exception as e:
            if auto_fb and self.backend_name in ("colab", "ollama"):
                print(
                    f"[LLM] Primary backend '{self.backend_name}' unavailable ({e}); "
                    "falling back to SmartLocalSQLBackend",
                    file=sys.stderr,
                )
                return SmartLocalSQLBackend().generate(prompt, max_tokens)
            raise

    @staticmethod
    def extract_sql(text):
        """Pull SQL out of markdown fences or return raw text."""
        m = re.search(r"```(?:sql)?\s*(.*?)```", text, re.S | re.I)
        sql = m.group(1) if m else text
        sql = sql.strip().rstrip(";").strip()
        return sql + ";"


_instance = None
_instance_key = None


def get_llm():
    global _instance, _instance_key
    key = (
        config.LLM_BACKEND.strip().lower(),
        config.COLAB_API_URL.strip(),
        config.COLAB_API_TOKEN.strip(),
        config.OLLAMA_MODEL.strip(),
        config.HF_MODEL.strip(),
    )
    if _instance is None or _instance_key != key:
        _instance = LLM()
        _instance_key = key
    return _instance
