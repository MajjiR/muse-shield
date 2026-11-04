"""Launch the er-v3 variants in parallel, one dedicated B200 trainer each (scripts/sft_entry.py).

    python3 scripts/er_v3_launch.py --data runs/er/v3 --variants A B C D

Each variant gets results/training/<run>_glimmer-er-v3<x>/ with config.json and run.log, and saves a promotable
(sampler) checkpoint every --checkpoint-every steps so scripts/er_ckpt_watch.py can score it while training runs.
The trainer job is deleted by the cookbook loop when the run ends; the final model is muse-shield-glimmer-er-v3<x>.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402

VENV_PY = "/Volumes/MajjiR/ai/venv-fwtrain/bin/python"
COOKBOOK = "/Volumes/MajjiR/ai/fw-cookbook"
SHAPE = "accounts/fireworks/trainingShapes/muse-glimmer-30b-131k-lora"
ENV_FILE = Path("/Users/majjir/muse-shield/.env")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=REPO / "runs/er/v3")
    ap.add_argument("--variants", nargs="+", default=["A", "B", "C", "D"])
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--epochs", type=int, default=1)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--checkpoint-every", type=int, default=200)
    a = ap.parse_args()
    env = dict(os.environ)
    for line in ENV_FILE.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, _, v = line.partition("=")
            env.setdefault(k.strip(), v.strip().strip('"'))
    git, started = git_version(), time.time()
    runs = {}
    for v in a.variants:
        out = RESULTS / "training" / new_run_id(f"glimmer-er-v3{v.lower()}", started, git)
        out.mkdir(parents=True, exist_ok=True)
        train = (a.data / v / "train.jsonl").resolve()
        cfg = {
            "cookbook_training_dir": COOKBOOK, "log_path": str(out / "trainer"),
            "base_model": "accounts/fireworks/models/muse-glimmer-30b", "tokenizer_model": "meta-models/Muse-Glimmer-30B",
            "renderer_name": "muse_glimmer", "train_file": str(train), "eval_file": str((a.data / v / "val.jsonl").resolve()),
            "lora_rank": a.rank, "learning_rate": a.lr, "epochs": a.epochs, "batch_size": a.batch, "max_seq_len": 6144,
            "warmup_steps": 0, "checkpoint_every": a.checkpoint_every, "save_final_checkpoint": True,
            "output_model_id": f"muse-shield-glimmer-er-v3{v.lower()}", "max_examples": None, "training_shape": SHAPE,
        }
        (out / "config.json").write_text(json.dumps(cfg, indent=1))
        rows = sum(1 for _ in train.open())
        (out / "data-stats.json").write_text(json.dumps({"rows": rows, "steps_per_epoch": rows // a.batch,
                                                         "manifest": json.loads((a.data / "manifest.json").read_text())}, indent=1))
        log = open(out / "run.log", "w")
        p = subprocess.Popen([VENV_PY, str(REPO / "scripts/sft_entry.py"), "--config", str(out / "config.json")],
                             cwd=f"{COOKBOOK}/training", env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        runs[v] = {"dir": str(out), "pid": p.pid, "rows": rows, "model": cfg["output_model_id"]}
        print(f"{v}: pid {p.pid}, {rows} rows (~{rows // a.batch} steps), {out}", flush=True)
    (a.data / "launched.json").write_text(json.dumps(runs, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
