"""
QLoRA fine-tuning of the same Qwen2.5-Coder 7B Instruct base used by Ollama.

Run on a CUDA GPU host from the repository root:
    python finetune/train_lora.py
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import config
from core.prompts import sql_generation_prompt

OUTPUT_DIR = "finetune/out/lora"
MODEL_NAME = "Qwen/Qwen2.5-Coder-7B-Instruct"
MAX_LENGTH = 1024


def load_examples():
    """Load only the project's curated examples; keep the gold eval set untouched."""
    with open(config.EXAMPLES_PATH, encoding="utf-8") as f:
        examples = json.load(f)
    if not examples:
        raise ValueError(f"No training examples found in {config.EXAMPLES_PATH}")
    return [{"question": row["q"], "sql": row["sql"]} for row in examples]


def get_schema():
    from sqlalchemy import create_engine, inspect

    engine = create_engine(config.DATABASE_URL)
    inspector = inspect(engine)
    schema = "\n".join(
        f"{table}({', '.join(column['name'] for column in inspector.get_columns(table))})"
        for table in inspector.get_table_names()
    )
    engine.dispose()
    if not schema:
        raise RuntimeError(f"No tables found in database {config.DATABASE_URL}")
    return schema


def tokenize_examples(examples, schema, tokenizer, max_length=MAX_LENGTH):
    """Tokenize prompt/SQL pairs and mask prompt tokens from the training loss."""
    records = []
    for example in examples:
        prompt = sql_generation_prompt(
            example["question"],
            example.get("schema", schema),
        )
        answer = f"\n```sql\n{example['sql'].strip()}\n```{tokenizer.eos_token}"
        prompt_ids = tokenizer(prompt, add_special_tokens=True)["input_ids"]
        full_ids = tokenizer(
            prompt + answer,
            add_special_tokens=True,
            truncation=True,
            max_length=max_length,
        )["input_ids"]
        prompt_length = min(len(prompt_ids), len(full_ids))
        labels = [-100] * prompt_length + full_ids[prompt_length:]
        if not any(label != -100 for label in labels):
            raise ValueError(
                f"SQL answer was truncated for question: {example['question']}"
            )
        records.append({
            "input_ids": full_ids,
            "attention_mask": [1] * len(full_ids),
            "labels": labels,
        })
    return records


def train():
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError(
            "QLoRA training requires a CUDA GPU. Run this script on a GPU host "
            "(for example, Google Colab with a GPU runtime)."
        )

    from datasets import Dataset
    from peft import LoraConfig, TaskType, get_peft_model, prepare_model_for_kbit_training
    from transformers import (
        AutoModelForCausalLM,
        AutoTokenizer,
        BitsAndBytesConfig,
        DataCollatorForSeq2Seq,
        Trainer,
        TrainingArguments,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.eos_token is None:
        raise RuntimeError(f"{MODEL_NAME} tokenizer has no EOS token")
    tokenizer.pad_token = tokenizer.eos_token

    quantization = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_compute_dtype=torch.bfloat16
        if torch.cuda.is_bf16_supported()
        else torch.float16,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
    )
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME,
        quantization_config=quantization,
        device_map="auto",
    )
    model.config.use_cache = False
    model = prepare_model_for_kbit_training(model)
    model = get_peft_model(
        model,
        LoraConfig(
            r=16,
            lora_alpha=32,
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
            lora_dropout=0.05,
            bias="none",
            task_type=TaskType.CAUSAL_LM,
        ),
    )
    model.print_trainable_parameters()

    examples = load_examples()
    records = tokenize_examples(examples, get_schema(), tokenizer)
    dataset = Dataset.from_list(records)
    print(f"Training {MODEL_NAME} on {len(dataset)} project examples")

    training_args = TrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=3,
        per_device_train_batch_size=1,
        gradient_accumulation_steps=8,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        gradient_checkpointing=True,
        logging_steps=1,
        save_strategy="epoch",
        save_total_limit=2,
        optim="paged_adamw_8bit",
        report_to="none",
    )
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=dataset,
        data_collator=DataCollatorForSeq2Seq(
            tokenizer=tokenizer,
            model=model,
            label_pad_token_id=-100,
            pad_to_multiple_of=8,
        ),
    )
    trainer.train()
    trainer.save_model(OUTPUT_DIR)
    tokenizer.save_pretrained(OUTPUT_DIR)
    print(f"LoRA adapter saved to {OUTPUT_DIR}")
    print("Next: run python finetune/merge.py, then convert and import the GGUF into Ollama.")


if __name__ == "__main__":
    train()
