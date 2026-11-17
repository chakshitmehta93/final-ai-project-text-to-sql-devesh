import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest

from core.prompts import sql_generation_prompt
from finetune.train_lora import load_examples, tokenize_examples


class CharacterTokenizer:
    eos_token = "<eos>"

    def __call__(self, text, **kwargs):
        ids = [ord(char) for char in text]
        if kwargs.get("truncation"):
            ids = ids[:kwargs["max_length"]]
        return {"input_ids": ids}


def test_finetune_uses_project_examples():
    assert load_examples()


def test_finetune_masks_inference_prompt_and_trains_sql_completion():
    example = {"question": "Count students", "sql": "SELECT COUNT(*) FROM students;"}
    schema = "students(student_id)"
    tokenizer = CharacterTokenizer()

    record = tokenize_examples([example], schema, tokenizer)[0]
    prompt = sql_generation_prompt(example["question"], schema)
    completion = f"\n```sql\n{example['sql']}\n```{tokenizer.eos_token}"
    prompt_length = len(prompt)

    assert record["input_ids"][:prompt_length] == [ord(char) for char in prompt]
    assert record["labels"][:prompt_length] == [-100] * prompt_length
    assert record["labels"][prompt_length:] == [ord(char) for char in completion]


def test_finetune_rejects_truncated_sql_completion():
    with pytest.raises(ValueError, match="SQL answer was truncated"):
        tokenize_examples(
            [{"question": "Count students", "sql": "SELECT COUNT(*) FROM students;"}],
            "students(student_id)",
            CharacterTokenizer(),
            max_length=2,
        )
