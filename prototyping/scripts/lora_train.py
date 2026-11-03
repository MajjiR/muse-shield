"""LoRA fine-tune Llama-3.2-1B-Instruct as the on-device privacy detector.

    .venv/bin/pip install -e '.[lora]'
    huggingface-cli login            # Llama 3.2 is gated: accept the license on Hugging Face first
    .venv/bin/privacy-engine lora-data --out runs/lora
    .venv/bin/python scripts/lora_train.py --data runs/lora --out adapters/detector-lora

Loss is computed on the assistant JSON only. Runs on Apple Silicon (MPS), CUDA or CPU.
A 1B model with r=16 on ~600 examples takes a few minutes on an M-series Mac.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer


def device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


def load_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def encode(row: dict, tok, max_len: int) -> dict:
    msgs = row["messages"]
    prompt = tok.apply_chat_template(msgs[:-1], add_generation_prompt=True, tokenize=True)
    full = tok.apply_chat_template(msgs, tokenize=True)
    labels = [-100] * len(prompt) + full[len(prompt):]
    return {"input_ids": full[:max_len], "labels": labels[:max_len]}


def batches(items: list[dict], size: int, pad_id: int, shuffle: bool):
    order = list(range(len(items)))
    if shuffle:
        random.shuffle(order)
    for i in range(0, len(order), size):
        chunk = [items[j] for j in order[i : i + size]]
        width = max(len(x["input_ids"]) for x in chunk)
        ids = torch.full((len(chunk), width), pad_id)
        labels = torch.full((len(chunk), width), -100)
        mask = torch.zeros((len(chunk), width), dtype=torch.long)
        for k, x in enumerate(chunk):
            n = len(x["input_ids"])
            ids[k, :n] = torch.tensor(x["input_ids"])
            labels[k, :n] = torch.tensor(x["labels"])
            mask[k, :n] = 1
        yield ids, labels, mask


@torch.no_grad()
def evaluate(model, data, args, pad_id, dev) -> float:
    model.eval()
    losses = [model(input_ids=i.to(dev), attention_mask=m.to(dev), labels=l.to(dev)).loss.item()
              for i, l, m in batches(data, args.batch, pad_id, shuffle=False)]
    model.train()
    return sum(losses) / max(len(losses), 1)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="meta-llama/Llama-3.2-1B-Instruct")
    ap.add_argument("--data", type=Path, default=Path("runs/lora"))
    ap.add_argument("--out", type=Path, default=Path("adapters/detector-lora"))
    ap.add_argument("--epochs", type=int, default=2)
    ap.add_argument("--batch", type=int, default=4)
    ap.add_argument("--accum", type=int, default=4)
    ap.add_argument("--lr", type=float, default=2e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max-len", type=int, default=768)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    random.seed(args.seed)
    torch.manual_seed(args.seed)
    dev = device()
    tok = AutoTokenizer.from_pretrained(args.base)
    pad_id = tok.pad_token_id if tok.pad_token_id is not None else tok.eos_token_id
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.float32 if dev == "cpu" else torch.bfloat16)
    model = get_peft_model(model, LoraConfig(
        r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )).to(dev)
    model.print_trainable_parameters()

    train = [encode(r, tok, args.max_len) for r in load_rows(args.data / "train.jsonl")]
    val = [encode(r, tok, args.max_len) for r in load_rows(args.data / "val.jsonl")]
    opt = torch.optim.AdamW([p for p in model.parameters() if p.requires_grad], lr=args.lr, weight_decay=0.0)
    steps = math.ceil(len(train) / args.batch / args.accum) * args.epochs
    sched = torch.optim.lr_scheduler.LambdaLR(opt, lambda s: min(1.0, (s + 1) / 10) * max(0.0, 1 - s / max(steps, 1)))

    print(f"device={dev} train={len(train)} val={len(val)} optimizer_steps={steps} val_loss={evaluate(model, val, args, pad_id, dev):.4f}")
    model.train()
    step, t0 = 0, time.time()
    for epoch in range(args.epochs):
        for i, (ids, labels, mask) in enumerate(batches(train, args.batch, pad_id, shuffle=True)):
            loss = model(input_ids=ids.to(dev), attention_mask=mask.to(dev), labels=labels.to(dev)).loss / args.accum
            loss.backward()
            if (i + 1) % args.accum == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                opt.step(); sched.step(); opt.zero_grad()
                step += 1
                if step % 10 == 0:
                    print(f"epoch {epoch} step {step}/{steps} loss {loss.item() * args.accum:.4f} {time.time() - t0:.0f}s")
        print(f"epoch {epoch} done · val_loss {evaluate(model, val, args, pad_id, dev):.4f}")

    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print(f"saved adapter to {args.out}")


if __name__ == "__main__":
    main()
