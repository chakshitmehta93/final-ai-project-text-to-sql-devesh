"""
finetune/merge.py
Merge LoRA adapter into the base model and save a full merged checkpoint.
After this, the pipeline auto-loads it from finetune/out/merged/ (see config.py).

Requires GPU and the adapter from train_lora.py.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

LORA_DIR  = "finetune/out/lora"
MERGE_DIR = "finetune/out/merged"
MODEL_NAME = "Qwen/Qwen2.5-Coder-3B-Instruct"


def merge():
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
    from peft import PeftModel

    print(f"loading base model {MODEL_NAME} ...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    base = AutoModelForCausalLM.from_pretrained(
        MODEL_NAME, torch_dtype=torch.float16, device_map="auto"
    )

    print(f"loading LoRA adapter from {LORA_DIR} ...")
    model = PeftModel.from_pretrained(base, LORA_DIR)

    print("merging ...")
    model = model.merge_and_unload()

    os.makedirs(MERGE_DIR, exist_ok=True)
    model.save_pretrained(MERGE_DIR)
    tokenizer.save_pretrained(MERGE_DIR)
    print(f"merged model saved to {MERGE_DIR}")
    print("The pipeline will auto-load it next time (config.best_hf_model()).")


if __name__ == "__main__":
    merge()
