import torch
from transformers import (
    DonutProcessor,
    VisionEncoderDecoderModel,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments,
)
from datasets import load_from_disk
from src.dataset import InvoiceDataset, cord_to_donut_json, sroie_to_donut_json, fatura_to_donut_json, donut_collate_fn
from pathlib import Path
import json

# ─── Config ─────────────────────────────────────────────────────────
MODEL_ID   = "models/best_model"   # onceki egitimden devam et
OUTPUT_DIR = "models/checkpoints_r2"
BEST_DIR   = "models/best_model"
MAX_LENGTH = 512
IMAGE_SIZE = (800, 1024)
EPOCHS     = 10
LR         = 1e-5               # devam egitiminde daha kucuk LR
FATURA_LIMIT = 700


def load_cord_samples(split: str) -> list:
    cord_raw = load_from_disk("data/raw/cord")
    samples = []
    for item in cord_raw[split]:
        samples.append({
            "image": item["image"],
            "target": cord_to_donut_json(item),
        })
    return samples


def load_sroie_samples() -> list:
    from PIL import Image as PILImage

    sroie_dir = Path("data/raw/sroie")
    img_dir = sroie_dir / "data" / "img"
    ann_dir = sroie_dir / "data" / "key"

    samples = []
    for ann_path in sorted(ann_dir.glob("*.json")):
        img_path = img_dir / ann_path.with_suffix(".jpg").name
        if not img_path.exists():
            img_path = img_dir / ann_path.with_suffix(".png").name
        if not img_path.exists():
            continue
        try:
            image = PILImage.open(img_path)
            target = sroie_to_donut_json(ann_path)
            samples.append({"image": image, "target": target})
        except Exception:
            continue
    return samples


def load_fatura_samples(max_samples: int = FATURA_LIMIT) -> list:
    try:
        fatura_raw = load_from_disk("data/raw/fatura")
        split = fatura_raw["train"]
        samples = []
        for item in split.select(range(min(max_samples, len(split)))):
            samples.append({
                "image": item["image"],
                "target": fatura_to_donut_json(item),
            })
        return samples
    except Exception as e:
        print(f"[warn] FATURA yuklenemedi: {e}")
        return []


def build_datasets(processor, sanity_check: bool = False):
    """Tüm veri setlerini yükler, InvoiceDataset nesneleri döndürür."""
    print("Veri setleri yukleniyor...")

    cord_train = load_cord_samples("train")
    cord_test  = load_cord_samples("test")
    sroie      = load_sroie_samples()
    fatura     = load_fatura_samples()

    train_samples = cord_train + sroie + fatura

    print(f"  CORD  train : {len(cord_train)}")
    print(f"  SROIE       : {len(sroie)}")
    print(f"  FATURA      : {len(fatura)}")
    print(f"  CORD  test  : {len(cord_test)}")
    print(f"  Toplam train: {len(train_samples)}")

    if sanity_check:
        # Sadece 50 train + 20 test ile hızlı doğrulama
        train_samples = train_samples[:50]
        cord_test     = cord_test[:20]
        print(f"  [SANITY CHECK] 50 train / 20 test ile calisiliyor")

    train_ds = InvoiceDataset(train_samples, processor, MAX_LENGTH, IMAGE_SIZE)
    test_ds  = InvoiceDataset(cord_test,     processor, MAX_LENGTH, IMAGE_SIZE)
    return train_ds, test_ds


def build_trainer(model, processor, train_ds, test_ds, epochs: int = EPOCHS):
    warmup_steps = max(1, int(len(train_ds) / 8 * epochs * 0.05))  # ~%5 warmup

    training_args = Seq2SeqTrainingArguments(
        output_dir=OUTPUT_DIR,
        num_train_epochs=epochs,
        learning_rate=LR,
        weight_decay=0.01,
        warmup_steps=warmup_steps,

        # VRAM kritik ayarlar — RTX 3050 6GB
        per_device_train_batch_size=1,
        per_device_eval_batch_size=1,
        gradient_accumulation_steps=8,
        fp16=True,
        optim="adamw_bnb_8bit",

        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        save_total_limit=3,

        logging_steps=10,
        report_to="none",

        predict_with_generate=True,
        generation_max_length=MAX_LENGTH,
    )

    return Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=test_ds,
        data_collator=donut_collate_fn,
    )


def load_model(model_id: str = MODEL_ID):
    print(f"Model yukleniyor: {model_id}")
    processor = DonutProcessor.from_pretrained(model_id)
    model = VisionEncoderDecoderModel.from_pretrained(model_id)

    model.config.pad_token_id = processor.tokenizer.pad_token_id
    model.config.eos_token_id = processor.tokenizer.eos_token_id
    model.config.decoder_start_token_id = processor.tokenizer.convert_tokens_to_ids(["<s_cord-v2>"])[0]
    # transformers 5.x: max_length generation_config'e gitmeli
    model.generation_config.max_length = MAX_LENGTH
    model.gradient_checkpointing_enable()
    return model, processor


def main(sanity_check: bool = False):
    print(f"CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        props = torch.cuda.get_device_properties(0)
        vram  = round(props.total_memory / 1024**3, 1)
        print(f"GPU : {props.name} ({vram} GB)")

    model, processor = load_model()
    train_ds, test_ds = build_datasets(processor, sanity_check=sanity_check)

    epochs = 1 if sanity_check else EPOCHS
    trainer = build_trainer(model, processor, train_ds, test_ds, epochs=epochs)

    print(f"\nEgitim basliyor — {epochs} epoch, {len(train_ds)} ornek")
    print(f"IMAGE_SIZE={IMAGE_SIZE}  MAX_LENGTH={MAX_LENGTH}  LR={LR}\n")

    trainer.train()

    if not sanity_check:
        Path(BEST_DIR).mkdir(parents=True, exist_ok=True)
        model.save_pretrained(BEST_DIR)
        processor.save_pretrained(BEST_DIR)
        print(f"\nModel kaydedildi: {BEST_DIR}")
    else:
        print("\n[SANITY CHECK] Basarili — tam egitim icin: python -m src.train")


if __name__ == "__main__":
    import sys
    sanity = "--sanity" in sys.argv
    main(sanity_check=sanity)
