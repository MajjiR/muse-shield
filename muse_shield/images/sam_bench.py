"""Local SAM 3 vs cloud SAM 3.1: faces found, false alarms, box agreement, speed.

    # start one or more local servers (ML venv on the SSD), e.g. fp32 on 8790 and fp16 on 8791
    MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.images.sam_bench \\
        --local fp32=http://127.0.0.1:8790/v1 --local fp16=http://127.0.0.1:8791/v1 \\
        --photo /path/bus.jpg=3 --photo /path/zidane.jpg=2

Images: real photos with a known face count, plus the synthetic samples, where "face" must find
nothing (they hold an illustrated ID portrait at most). Cloud SAM 3.1 is the reference for box
agreement (mean IoU of matched boxes). Latency is the median of --repeat warm calls per image.
"""

from __future__ import annotations

import argparse
import io
import os
import statistics
import sys
import time
from pathlib import Path

from ..config import load_env
from ..results import git_version, save_run
from .meta import Box, Sam
from .samples import all_samples

META_URL = "https://api.meta.ai/v1"


def iou(a: Box, b: Box) -> float:
    w = min(a.x2, b.x2) - max(a.x1, b.x1)
    h = min(a.y2, b.y2) - max(a.y1, b.y1)
    inter = max(0, w) * max(0, h)
    union = a.area + b.area - inter
    return inter / union if union else 0.0


def match(pred: list[Box], ref: list[Box]) -> list[float]:
    """Greedy one-to-one matching by IoU; returns the IoU of each matched pair."""
    pairs = sorted(((iou(p, r), i, j) for i, p in enumerate(pred) for j, r in enumerate(ref)), reverse=True)
    used_p, used_r, out = set(), set(), []
    for v, i, j in pairs:
        if v > 0.1 and i not in used_p and j not in used_r:
            used_p.add(i), used_r.add(j), out.append(v)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.images.sam_bench")
    ap.add_argument("--local", action="append", default=[], help="NAME=BASE_URL of a local SAM server, repeatable")
    ap.add_argument("--photo", action="append", default=[], help="PATH=FACES, repeatable")
    ap.add_argument("--concept", default="face")
    ap.add_argument("--repeat", type=int, default=3)
    ap.add_argument("--tag", default="sam-local-vs-cloud")
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args(argv)
    load_env()

    images: list[tuple[str, bytes, str, int | None]] = []  # name, bytes, mime, expected faces (None = unknown)
    for spec in args.photo:
        path, _, n = spec.rpartition("=")
        p = Path(path)
        images.append((p.name, p.read_bytes(), "image/png" if p.suffix == ".png" else "image/jpeg", int(n)))
    for s in all_samples():
        buf = io.BytesIO()
        s.image.save(buf, "PNG")
        images.append((s.name, buf.getvalue(), "image/png", None if s.photos else 0))

    backends = {"cloud sam-3.1": Sam(os.environ.get("META_BASE_URL", META_URL), os.environ.get("MODEL_API_KEY", ""))}
    for spec in args.local:
        name, _, url = spec.partition("=")
        backends[f"local sam3 {name}"] = Sam(url, "local", model=f"sam3-local-{name}")

    started, git = time.time(), git_version()
    runs: dict[str, list[dict]] = {}
    for bname, sam in backends.items():
        rows = []
        for name, data, mime, want in images:
            times, boxes = [], []
            for _ in range(args.repeat):
                t0 = time.perf_counter()
                boxes, _ = sam.boxes(data, mime, args.concept)
                times.append((time.perf_counter() - t0) * 1000)
            rows.append({"image": name, "faces_expected": want, "faces_found": len(boxes),
                         "boxes": [b.as_list() for b in boxes], "ms": [round(t) for t in times],
                         "ms_median": round(statistics.median(times))})
            print(f"{bname:22} {name:18} found {len(boxes)} (want {want}) {statistics.median(times):7.0f} ms", flush=True)
        runs[bname] = rows

    ref = {r["image"]: [Box(*b) for b in r["boxes"]] for r in runs["cloud sam-3.1"]}
    reports, lines = [], ["| backend | faces found (photos) | false alarms (no-face images) | box IoU vs cloud | median ms per call |",
                          "|---|---|---|---|---|"]
    for bname, rows in runs.items():
        photos = [r for r in rows if r["faces_expected"]]
        negatives = [r for r in rows if r["faces_expected"] == 0]
        found = sum(min(r["faces_found"], r["faces_expected"]) for r in photos)
        wanted = sum(r["faces_expected"] for r in photos)
        false = sum(r["faces_found"] for r in negatives)
        ious = [v for r in rows for v in match([Box(*b) for b in r["boxes"]], ref[r["image"]])]
        med = statistics.median([r["ms_median"] for r in rows])
        rep = {"backend": bname.replace(" ", "_"), "model": bname, "docs": len(rows),
               "span_recall": found / wanted if wanted else None, "false_alarms": false,
               "mean_iou_vs_cloud": round(sum(ious) / len(ious), 3) if ious else None,
               "latency_ms_median": med, "seconds": round(time.time() - started, 1), "cost_usd": None,
               "cost": {"usd": None, "basis": "tokens", "detail": {"note": "SAM pricing not published; local runs are free"}}}
        reports.append(rep)
        lines.append(f"| {bname} | {found}/{wanted} | {false} | {rep['mean_iou_vs_cloud']} | {med:.0f} |")
    compare = "\n".join([f"# SAM: local vs cloud, concept \"{args.concept}\"", ""] + lines)
    print("\n" + compare)
    if args.no_record:
        return 0
    out = save_run("sam-local-vs-cloud", args.tag, reports, {r["backend"]: runs[r["model"]] for r in reports},
                   when=started, git=git, compare_md=compare,
                   settings={r["backend"]: {"concept": args.concept, "repeat": args.repeat} for r in reports},
                   dataset={"photos": len(args.photo), "synthetic": len(images) - len(args.photo)})
    print(f"saved {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
