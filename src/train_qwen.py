"""
Qwen2.5-1.5B modelini fatura analizi icin LoRA ile fine-tune eder.
Calistir: python -m src.train_qwen
"""
import sys, json, torch
from pathlib import Path
from datasets import Dataset
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    BitsAndBytesConfig,
)
from peft import LoraConfig, get_peft_model, TaskType
from trl import SFTTrainer, SFTConfig

# ─── Config ──────────────────────────────────────────────────────────
MODEL_ID   = "Qwen/Qwen2.5-1.5B-Instruct"
DATA_PATH  = Path("data/synthetic/invoice_analysis_train.jsonl")
OUTPUT_DIR = "models/qwen_lora"
BEST_DIR   = "models/qwen_best"
MAX_LENGTH = 256
EPOCHS     = 3
LR         = 2e-4
BATCH_SIZE = 1
GRAD_ACCUM = 8   # efektif batch = 8


# ─── Veri yukleme ────────────────────────────────────────────────────

def load_data() -> Dataset:
    records = []
    with open(DATA_PATH, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            # Chat formatina donustur
            text = (
                f"<|im_start|>user\n{rec['instruction']}<|im_end|>\n"
                f"<|im_start|>assistant\n{rec['output']}<|im_end|>"
            )
            records.append({"text": text})
    return Dataset.from_list(records)


# ─── Model yukleme ───────────────────────────────────────────────────

def load_model_and_tokenizer():
    print(f"Model yukleniyor: {MODEL_ID}")

    # 4-bit quantization — 6GB VRAM'e sigar
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=True,
    )

    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        quantization_config=bnb_config,
        device_map="auto",
        trust_remote_code=True,
    )
    model.config.use_cache = False

    return model, tokenizer


# ─── LoRA config ─────────────────────────────────────────────────────

def apply_lora(model):
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=8,                           # rank — VRAM tasarrufu
        lora_alpha=32,
        lora_dropout=0.05,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj"],
        bias="none",
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


# ─── Egitim ──────────────────────────────────────────────────────────

def main():
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        print(f"GPU: {props.name} ({round(props.total_memory/1024**3,1)} GB)")

    dataset = load_data()
    print(f"Veri: {len(dataset)} ornek yuklendi")

    # Train / val bolumu
    split = dataset.train_test_split(test_size=0.05, seed=42)
    train_ds = split["train"]
    val_ds   = split["test"]
    print(f"Train: {len(train_ds)} | Val: {len(val_ds)}")

    model, tokenizer = load_model_and_tokenizer()
    model = apply_lora(model)

    training_args = SFTConfig(
        output_dir=OUTPUT_DIR,
        num_train_epochs=EPOCHS,
        learning_rate=LR,
        per_device_train_batch_size=BATCH_SIZE,
        per_device_eval_batch_size=BATCH_SIZE,
        gradient_accumulation_steps=GRAD_ACCUM,
        warmup_ratio=0.05,
        lr_scheduler_type="cosine",
        bf16=True,
        fp16=False,
        optim="paged_adamw_8bit",
        max_length=MAX_LENGTH,
        dataset_text_field="text",
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        save_total_limit=2,
        logging_steps=20,
        report_to="none",
    )

    trainer = SFTTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=val_ds,
        processing_class=tokenizer,
    )

    print(f"\nEgitim basliyor — {EPOCHS} epoch, {len(train_ds)} ornek")
    trainer.train()

    # LoRA adaptoru kaydet
    Path(BEST_DIR).mkdir(parents=True, exist_ok=True)
    model.save_pretrained(BEST_DIR)
    tokenizer.save_pretrained(BEST_DIR)
    print(f"\nModel kaydedildi: {BEST_DIR}")


if __name__ == "__main__":
    main()
