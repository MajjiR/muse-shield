"""Follow a Fireworks training log and save plottable per-step metrics.

    python3 scripts/training_logger.py <launch.log> <results/training/<run>/> [--started-epoch FILE]

Writes, and keeps updating until the log reports exit=:
    steps.csv    step, epoch, loss, grad_norm, grad_norm_rms, grad_norm_post_clip, observed_utc, elapsed_s
    steps.jsonl  the same rows as JSON, with every field the trainer logged
    evals.jsonl  held-out scores the starter prints (base before training, tuned after)

`observed_utc` is when the logger saw the line. Steps already in the log when the
logger starts are marked `backfilled` and have no time, since the trainer's lines carry none.
"""

from __future__ import annotations

import csv
import json
import sys
import time
from pathlib import Path

FIELDS = ["step", "epoch", "loss", "grad_norm", "grad_norm_rms", "grad_norm_post_clip", "observed_utc", "elapsed_s", "backfilled"]


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    log, out = Path(argv[1]), Path(argv[2])
    started = None
    if "--started-epoch" in argv:
        started = float(Path(argv[argv.index("--started-epoch") + 1]).read_text().strip())
    out.mkdir(parents=True, exist_ok=True)
    seen_steps: set[int] = set()
    seen_evals: set[str] = set()
    backfill = True
    pos = 0
    while True:
        text = log.read_text(errors="replace") if log.exists() else ""
        new, pos = text[pos:], len(text)
        done = "exit=" in new
        rows, evals = [], []
        for line in new.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "step" in d and "loss" in d and "label" not in d and d["step"] not in seen_steps:
                seen_steps.add(d["step"])
                now = time.time()
                d.update({"observed_utc": None if backfill else time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                          "elapsed_s": None if backfill or started is None else round(now - started, 1),
                          "backfilled": backfill})
                rows.append(d)
            elif "label" in d and line not in seen_evals:
                seen_evals.add(line)
                evals.append({**d, "observed_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        if rows:
            new_csv = not (out / "steps.csv").exists()
            with (out / "steps.csv").open("a", newline="") as f:
                w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
                if new_csv:
                    w.writeheader()
                w.writerows(rows)
            with (out / "steps.jsonl").open("a") as f:
                f.writelines(json.dumps(r) + "\n" for r in rows)
        if evals:
            with (out / "evals.jsonl").open("a") as f:
                f.writelines(json.dumps(e) + "\n" for e in evals)
        backfill = False
        if done:
            return 0
        time.sleep(5)


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
