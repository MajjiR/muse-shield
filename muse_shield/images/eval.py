"""Image masking eval: synthetic images with pixel-exact gold, plus optional real photos for face counts.

    MUSE_SHIELD_DEV_RAW_ANALYSIS=1 .venv/bin/python -m muse_shield.images.eval --tag images5
    ... --photo /path/to/street.jpg=4        # also check that 4 faces get blurred (outputs stay in runs/)

Per gold value: masked when >= 80% of its pixels sit under a bar, leaked when it isn't masked or the
re-scan can still read it. Harmless lines (labels, totals, chit-chat) are over-masked when > 50% covered.
Synthetic before/after images and gallery.html are saved in the run folder; real photos go to runs/images/
only, since they aren't ours to publish.
"""

from __future__ import annotations

import argparse
import html
import io
import os
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from ..app.vault import Vault
from ..config import REPO_ROOT
from ..results import git_version, save_run
from . import ImageMasker, image_models_from_env
from .masker import BLUR_KINDS
from .meta import Box
from .samples import Sample, all_samples

MASKED_AT, OVERMASKED_AT = 0.8, 0.5


def coverage(box: Box, rects: list[Box], size: tuple[int, int]) -> float:
    """Share of box's pixels under any of rects."""
    if box.area == 0:
        return 0.0
    layer = Image.new("1", size, 0)
    d = ImageDraw.Draw(layer)
    for r in rects:
        d.rectangle(r.as_list(), fill=1)
    return sum(layer.crop(box.as_list()).getdata()) / box.area


def score(sample: Sample, result: dict) -> dict:
    size = sample.image.size
    bars = [(Box(*r["box"]), r["label"]) for r in result["regions"] if r["kind"] not in BLUR_KINDS]
    blurs = [Box(*r["box"]) for r in result["regions"] if r["kind"] in BLUR_KINDS]
    leaked_labels = set((result.get("verify") or {}).get("leaked") or [])
    gold = []
    for g in sample.gold:
        cov = coverage(g["box"], [b for b, _ in bars], size)
        labels = sorted({lab for b, lab in bars if b.overlap(g["box"]) > 0})
        reread = bool(leaked_labels & set(labels))
        gold.append({"value": g["value"], "type": g["type"], "coverage": round(cov, 3), "labels": labels,
                     "masked": cov >= MASKED_AT, "leaked": cov < MASKED_AT or reread})
    keep = [{"text": k["text"], "coverage": round(c, 3), "overmasked": c > OVERMASKED_AT}
            for k in sample.keep for c in [coverage(k["box"], [b for b, _ in bars], size)]]
    photos = [{"box": p.as_list(), "blurred": coverage(p, blurs, size) >= MASKED_AT} for p in sample.photos]
    return {"name": sample.name, "gold": gold, "keep": keep, "photos": photos}


def run_photo(masker: ImageMasker, path: Path, faces: int, out_dir: Path) -> dict:
    t0 = time.perf_counter()
    m = masker.mask(path.read_bytes())
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{path.stem}.masked.png").write_bytes(m.image)
    found = sum(r["kind"] == "face" for r in m.regions)
    return {"name": path.name, "faces_expected": faces, "faces_blurred": found, "verify": m.verify,
            "seconds": round(time.perf_counter() - t0, 1), "cost": m.cost, "timings_ms": m.timings_ms}


def gallery(rows: list[dict], photos: list[dict]) -> str:
    cards = []
    for r in rows:
        g = r["score"]["gold"]
        miss = [f"{x['type']} “{html.escape(x['value'])}”" for x in g if x["leaked"]]
        over = [f"“{html.escape(x['text'])}”" for x in r["score"]["keep"] if x["overmasked"]]
        cards.append(f"""<section><h2>{html.escape(r['name'])}</h2>
<p>{sum(x['masked'] for x in g)}/{len(g)} values masked · leaked: {', '.join(miss) or 'none'} · over-masked: {', '.join(over) or 'none'}
· re-scan {'ok' if (r['verify'] or {}).get('ok') else 'FAILED'} · {r['seconds']} s</p>
<div class="pair"><figure><img src="{r['name']}.png" alt=""><figcaption>original (synthetic)</figcaption></figure>
<figure><img src="{r['name']}.masked.png" alt=""><figcaption>what leaves the device after masking</figcaption></figure></div>
<details><summary>Masked text</summary><pre>{html.escape(r['masked_text'])}</pre></details></section>""")
    ph = "".join(f"<li>{html.escape(p['name'])}: {p['faces_blurred']} of {p['faces_expected']} faces blurred, re-scan "
                 f"{'ok' if (p['verify'] or {}).get('ok') else 'FAILED'}</li>" for p in photos)
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Image masking gallery</title><style>
:root{{--bg:#fff;--fg:#111;--muted:#666;--line:#e5e5e5}}
@media (prefers-color-scheme:dark){{:root{{--bg:#111;--fg:#eee;--muted:#999;--line:#333}}}}
body{{background:var(--bg);color:var(--fg);font:15px/1.5 -apple-system,system-ui,sans-serif;max-width:1200px;margin:0 auto;padding:24px 16px}}
h1{{font-size:22px}} h2{{font-size:17px;margin:28px 0 4px}} p,figcaption,li{{color:var(--muted)}}
.pair{{display:grid;grid-template-columns:1fr 1fr;gap:12px}} @media (max-width:700px){{.pair{{grid-template-columns:1fr}}}}
img{{width:100%;border:1px solid var(--line)}} pre{{white-space:pre-wrap;font-size:13px}} section{{border-top:1px solid var(--line)}}
</style></head><body><h1>Image masking: Muse Spark + SAM 3.1</h1>
<p>Synthetic images, made-up data. Bars carry the vault placeholder each value gets in chat.</p>
{''.join(cards)}{f'<h2>Real photos (images not published)</h2><ul>{ph}</ul>' if ph else ''}</body></html>"""


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m muse_shield.images.eval")
    ap.add_argument("--tag", default="images")
    ap.add_argument("--photo", action="append", default=[], help="PATH=EXPECTED_FACES, repeatable")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--no-record", action="store_true")
    args = ap.parse_args(argv)

    vision, sam, why = image_models_from_env()
    if not vision:
        print(why, file=sys.stderr)
        return 2
    started, git = time.time(), git_version()
    vault = Vault(Path(tempfile.mkdtemp()) / "eval.db", os.urandom(32))
    masker = ImageMasker(vault, vision, sam)
    samples = all_samples()

    def one(s: Sample) -> dict:
        buf = io.BytesIO()
        s.image.save(buf, "PNG")
        t0 = time.perf_counter()
        m = masker.mask(buf.getvalue())
        d = m.to_dict(with_image=False)
        return {"name": s.name, "sample": s, "masked": m.image, "regions": d["regions"], "masked_text": d["masked_text"],
                "verify": d["verify"], "timings_ms": d["timings_ms"], "cost": d["cost"],
                "seconds": round(time.perf_counter() - t0, 1), "score": score(s, d)}

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        rows = list(pool.map(one, samples))
    photo_out = REPO_ROOT / "runs" / "images" / time.strftime("%Y%m%d-%H%M%S")
    photos = []
    for spec in args.photo:
        path, _, n = spec.rpartition("=")
        photos.append(run_photo(masker, Path(path), int(n), photo_out))

    gold = [g for r in rows for g in r["score"]["gold"]]
    keep = [k for r in rows for k in r["score"]["keep"]]
    ids = [p for r in rows for p in r["score"]["photos"]]
    by_type: dict[str, list[bool]] = {}
    for g in gold:
        by_type.setdefault(g["type"], []).append(g["masked"])
    usd = sum(r["cost"]["spark_usd"] or 0 for r in rows + photos)
    seconds = round(time.time() - started, 1)
    report = {
        "backend": "muse_spark+sam", "model": f"{vision.model} + sam-3.1", "docs": len(rows) + len(photos),
        "leak_rate": sum(g["leaked"] for g in gold) / len(gold), "span_recall": sum(g["masked"] for g in gold) / len(gold),
        "span_precision": None, "valid_rate": sum(1 for r in rows if (r["verify"] or {}).get("error") is None) / len(rows),
        "overmask_rate": sum(k["overmasked"] for k in keep) / len(keep),
        "id_photos_blurred": f"{sum(p['blurred'] for p in ids)}/{len(ids)}",
        "faces": [{k: p[k] for k in ("name", "faces_expected", "faces_blurred")} for p in photos],
        "rescan_ok": f"{sum(1 for r in rows if (r['verify'] or {}).get('ok'))}/{len(rows)}",
        "recall_by_type": {t: sum(v) / len(v) for t, v in sorted(by_type.items())},
        "latency_s": {"p50": sorted(r["seconds"] for r in rows)[len(rows) // 2], "max": max(r["seconds"] for r in rows)},
        "sam_requests": sum(r["cost"]["sam_requests"] for r in rows + photos),
        "seconds": seconds, "cost_usd": usd,
        "cost": {"usd": usd, "basis": "tokens", "detail": {"note": "Muse Spark tokens only; SAM 3.1 requests are counted, not priced"}},
    }
    lines = [f"# Image masking · {report['model']}", "",
             f"- values masked: {report['span_recall']:.1%} · leaked (incl. re-scan): {report['leak_rate']:.1%} · "
             f"harmless text over-masked: {report['overmask_rate']:.1%}",
             f"- ID photos blurred: {report['id_photos_blurred']} · re-scan ok: {report['rescan_ok']} · "
             f"p50 {report['latency_s']['p50']} s per image · Spark ${usd:.4f} + {report['sam_requests']} SAM requests", "",
             "| image | masked | leaked | over-masked | re-scan | s |", "|---|---|---|---|---|---|"]
    for r in rows:
        g, k = r["score"]["gold"], r["score"]["keep"]
        lines.append(f"| {r['name']} | {sum(x['masked'] for x in g)}/{len(g)} | "
                     f"{', '.join(x['value'] for x in g if x['leaked']) or '–'} | "
                     f"{', '.join(x['text'] for x in k if x['overmasked']) or '–'} | "
                     f"{'ok' if (r['verify'] or {}).get('ok') else 'FAIL'} | {r['seconds']} |")
    for p in photos:
        lines.append(f"| {p['name']} (photo) | faces {p['faces_blurred']}/{p['faces_expected']} | | | "
                     f"{'ok' if (p['verify'] or {}).get('ok') else 'FAIL'} | {p['seconds']} |")
    compare = "\n".join(lines)
    print(compare)
    if args.no_record:
        return 0
    preds = [{k: r[k] for k in ("name", "regions", "masked_text", "verify", "timings_ms", "cost", "seconds", "score")}
             for r in rows] + photos
    out = save_run("image-masking", args.tag, [report], {"muse_spark+sam": preds}, when=started, git=git,
                   settings={"muse_spark+sam": {"vision_model": vision.model, "reasoning_effort": vision.reasoning_effort,
                                                "sam_concepts": list(masker.concepts), "masked_at": MASKED_AT,
                                                "overmasked_at": OVERMASKED_AT}},
                   dataset={"name": "muse_shield.images.samples", "synthetic": len(rows), "photos": len(photos),
                            "gold_values": len(gold), "harmless_lines": len(keep)},
                   compare_md=compare)
    for r in rows:
        r["sample"].image.save(out / f"{r['name']}.png")
        (out / f"{r['name']}.masked.png").write_bytes(r["masked"])
    (out / "gallery.html").write_text(gallery(rows, photos))
    print(f"\nsaved {out.relative_to(REPO_ROOT)}" + (f"; photo outputs in {photo_out}" if photos else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
