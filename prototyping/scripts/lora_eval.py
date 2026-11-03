"""Compare the base model and the LoRA adapter as privacy detectors on held-out data.

    .venv/bin/python scripts/lora_eval.py --data runs/lora --adapter adapters/detector-lora

Scores use the runtime parser (privacy_engine.detector.llm.parse_response), so
hallucinated spans are dropped exactly as they would be in production.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer

from privacy_engine.detector.llm import parse_response


def device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    return "cuda" if torch.cuda.is_available() else "cpu"


@torch.no_grad()
def predict(model, tok, messages, dev) -> str:
    ids = tok.apply_chat_template(messages, add_generation_prompt=True, return_tensors="pt").to(dev)
    out = model.generate(ids, max_new_tokens=256, do_sample=False, pad_token_id=tok.eos_token_id)
    return tok.decode(out[0, ids.shape[1]:], skip_special_tokens=True)


def score(model, tok, rows, dev) -> dict:
    tp = fp = fn = conf_ok = 0
    t0 = time.time()
    for row in rows:
        text = row["messages"][1]["content"]
        gold = json.loads(row["messages"][2]["content"])
        ents, ctx = parse_response(predict(model, tok, row["messages"][:2], dev), text)
        pred = {(e.text, e.type.value) for e in ents}
        want = {(e["text"], e["type"]) for e in gold["entities"]}
        tp += len(pred & want); fp += len(pred - want); fn += len(want - pred)
        conf_ok += ctx.confidential == gold["confidential"]
    p = tp / max(tp + fp, 1)
    r = tp / max(tp + fn, 1)
    return {"precision": p, "recall": r, "f1": 2 * p * r / max(p + r, 1e-9),
            "confidential_acc": conf_ok / len(rows), "ms_per_example": (time.time() - t0) * 1000 / len(rows)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="meta-llama/Llama-3.2-1B-Instruct")
    ap.add_argument("--data", type=Path, default=Path("runs/lora"))
    ap.add_argument("--adapter", type=Path, default=Path("adapters/detector-lora"))
    ap.add_argument("--limit", type=int, default=60)
    args = ap.parse_args()

    dev = device()
    rows = [json.loads(l) for l in (args.data / "val.jsonl").read_text().splitlines() if l.strip()][: args.limit]
    tok = AutoTokenizer.from_pretrained(args.base)
    model = AutoModelForCausalLM.from_pretrained(args.base, torch_dtype=torch.bfloat16 if dev != "cpu" else torch.float32).to(dev)
    base = score(model, tok, rows, dev)
    model = PeftModel.from_pretrained(model, args.adapter).to(dev)
    tuned = score(model, tok, rows, dev)

    print(f"{'':12} {'precision':>9} {'recall':>7} {'f1':>6} {'conf acc':>8} {'ms/ex':>7}")
    for name, s in (("base", base), ("lora", tuned)):
        print(f"{name:12} {s['precision']:9.2%} {s['recall']:7.2%} {s['f1']:6.2%} {s['confidential_acc']:8.2%} {s['ms_per_example']:7.0f}")


if __name__ == "__main__":
    main()
