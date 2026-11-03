"""Run the Fireworks cookbook SFT loop (serverless) with Muse Shield's settings. Called by robust_train.py.

Runs with the cookbook venv from the cookbook's `training/` directory:
    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/sft_entry.py --config run.json

Settings match the muse_glimmer_starter that v1 used: LoRA rank 8 / alpha 32, constant learning
rate, Adam (0.9, 0.999, 1e-8), no weight decay, gradient clipping at 1.0, loss on the last
assistant turn only (the gold JSON, not the worked example in every prompt). On top of the
starter it saves resumable and promotable checkpoints periodically, so a crash resumes instead
of restarting, and an early stop still leaves a model to promote.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args()
    c = json.loads(args.config.read_text())
    sys.path.insert(0, c["cookbook_training_dir"])

    import training.recipes.sft_loop as sft_loop  # noqa: E402

    cfg = sft_loop.Config(
        serverless=True,
        log_path=c["log_path"],
        base_model=c["base_model"],
        tokenizer_model=c["tokenizer_model"],
        renderer_name=c["renderer_name"],
        dataset=c["train_file"],
        evaluation_dataset=c.get("eval_file", ""),
        train_on_what="last_assistant_turn",
        lora_rank=c["lora_rank"],
        lora_alpha=c.get("lora_alpha", 32),
        learning_rate=c["learning_rate"],
        epochs=c["epochs"],
        batch_size=c["batch_size"],
        max_seq_len=c["max_seq_len"],
        grad_clip_norm=c.get("grad_clip_norm", 1.0),
        weight_decay=c.get("weight_decay", 0.0),
        warmup_steps=c.get("warmup_steps", 0),
        dcp_save_interval=c["checkpoint_every"],
        sampler_save_interval=c["checkpoint_every"],
        init_from_checkpoint=c.get("init_from_checkpoint") or None,
        output_model_id=c.get("output_model_id") or None,
        max_examples=c.get("max_examples"),
    )
    sft_loop.main(cfg)
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", stream=sys.stdout)
    raise SystemExit(main())
