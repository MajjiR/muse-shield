"""Score models on the entity-resolution test sets (same prompt, parser and scorer for every model).

    # base Glimmer or a training checkpoint, through the Training API sampler (no deployment):
    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/er_eval.py --backend sampler --tag base-glimmer
    # a deployed model (live-merge deployment of the fine-tune), OpenAI-compatible:
    ... --backend glimmer --model 'accounts/<acct>/models/<id>#accounts/<acct>/deployments/<dep>' --tag er-v1
    # cloud Muse Spark as the frontier reference (synthetic documents only):
    ... --backend muse_spark --tag spark-low

Reports leak and core leak, mention F1, coreference (pairwise link) F1, owner accuracy (with UNKNOWN
handled separately), type and amount-role accuracy, relation F1, and how many people were resolved
to exactly one identity. Results go to results/entity-resolution/<time>_v<ver>+<sha>_<tag>/.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from muse_shield import resolution as R  # noqa: E402
from muse_shield.analysis import ContractError  # noqa: E402
from muse_shield.config import load_env  # noqa: E402
from muse_shield.results import RESULTS, git_version, new_run_id  # noqa: E402

COOKBOOK = Path("/Volumes/MajjiR/ai/fw-cookbook")
TOKENIZER = "meta-models/Muse-Glimmer-30B"
BASE = "accounts/fireworks/models/muse-glimmer-30b"


def sampler_call(model_path: str, max_tokens: int):
    sys.path.insert(0, str(COOKBOOK))
    from fireworks.training import tinker
    from fireworks.training.sdk import FiretitanServiceClient
    from training.renderer import get_text_content
    from training.utils.supervised import build_renderer
    from training.utils.tokenizers import load_tokenizer

    tok = load_tokenizer(TOKENIZER)
    renderer = build_renderer(tok, TOKENIZER, "muse_glimmer")
    service = FiretitanServiceClient(api_key=os.environ["FIREWORKS_API_KEY"], base_url="https://api.fireworks.ai/training/v1/serverless")
    sampler = service.create_sampling_client(model_path=model_path, tokenizer=tok) if model_path \
        else service.create_sampling_client(base_model=BASE, tokenizer=tok)

    def call(msgs):
        prompt = renderer.build_generation_prompt(msgs)
        out = sampler.sample(prompt=prompt, num_samples=1, sampling_params=tinker.SamplingParams(
            max_tokens=max_tokens, temperature=0.0, stop=renderer.get_stop_sequences())).result()
        toks = out.sequences[0].tokens
        msg, _ = renderer.parse_response(toks)
        return get_text_content(msg) or "", {"prompt_tokens": len(prompt.to_ints()) if hasattr(prompt, "to_ints") else 0,
                                             "completion_tokens": len(toks)}
    return call, model_path or BASE


def chat_call(backend: str, model: str, max_tokens: int):
    from muse_shield.backends import GlimmerBackend, MetaModelBackend
    if backend == "glimmer":
        b = GlimmerBackend("https://api.fireworks.ai/inference/v1", model, os.environ["FIREWORKS_API_KEY"],
                           max_tokens=max_tokens, timeout=300.0)
    else:  # muse_spark / muse_wonder: synthetic documents only
        b = MetaModelBackend(os.environ.get("META_BASE_URL", "https://api.meta.ai/v1"), model or "muse-spark-1.3",
                             os.environ.get("MODEL_API_KEY", ""), name=backend, synthetic_only=True,
                             reasoning_effort=os.environ.get("META_REASONING_EFFORT", "low"), max_tokens=max_tokens + 4000)
    return b._call, b.model


def run_one(call, doc: dict) -> dict:
    msgs = R.messages(doc["text"])
    t0, usage, raw, err = time.perf_counter(), {"prompt_tokens": 0, "completion_tokens": 0}, "", ""
    res = None
    for attempt in (1, 2):
        try:
            raw, u = call(msgs)
        except Exception as exc:  # noqa: BLE001 - a failed call counts as an invalid answer
            err = f"call failed: {exc!s:.120}"
            break
        for k in usage:
            usage[k] += u.get(k, 0)
        try:
            res = R.parse(raw, doc["text"])
            break
        except ContractError as exc:
            err = str(exc)
            msgs = msgs + [{"role": "assistant", "content": raw},
                           {"role": "user", "content": f"That output broke the contract ({err}). Reply with only the corrected JSON object."}]
    score = R.score_doc(doc, res)
    pred = None if res is None else {"entities": [{"id": e.id, "type": e.type, "role": e.role, "subtype": e.subtype,
                                                    "owner": e.owner, "mentions": [[m.start, m.end] for m in e.mentions]}
                                                   for e in res.entities], "relations": [list(r) for r in res.relations]}
    return {"uid": doc["uid"], "family": doc["family"], "score": score, "pred": pred, "error": err if res is None else "",
            "usage": usage, "latency_s": time.perf_counter() - t0}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", choices=["sampler", "glimmer", "muse_spark", "muse_wonder"], required=True)
    ap.add_argument("--model", default="", help="sampler checkpoint path, deployment route, or Meta model id")
    ap.add_argument("--data", type=Path, default=REPO / "runs/er/v1")
    ap.add_argument("--sets", nargs="+", default=["test", "challenge"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=24)
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--tag", required=True)
    a = ap.parse_args(argv)
    load_env()
    started, git = time.time(), git_version()
    call, model = sampler_call(a.model, a.max_tokens) if a.backend == "sampler" else chat_call(a.backend, a.model, a.max_tokens)
    out = RESULTS / "entity-resolution" / new_run_id(a.tag, started, git)
    out.mkdir(parents=True, exist_ok=True)
    report = {"backend": a.backend, "model": model, "tag": a.tag, "git": git, "sets": {}}
    for name in a.sets:
        docs = [json.loads(l) for l in (a.data / f"{name}.docs.jsonl").read_text().splitlines() if l.strip()]
        docs = docs[: a.limit] if a.limit else docs
        t0 = time.time()
        with ThreadPoolExecutor(a.workers) as pool:
            rows = list(pool.map(lambda d: run_one(call, d), docs))
        agg = R.aggregate([r["score"] for r in rows])
        agg["seconds"] = round(time.time() - t0, 1)
        agg["tokens"] = {k: sum(r["usage"][k] for r in rows) for k in ("prompt_tokens", "completion_tokens")}
        report["sets"][name] = agg
        (out / f"{name}.preds.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
        print(f"{name} ({len(docs)} docs): " + json.dumps({k: (round(v, 4) if isinstance(v, float) else v)
                                                              for k, v in agg.items() if not isinstance(v, dict)}), flush=True)
        for k in ("mention", "coref", "relations"):
            print(f"   {k}: P {agg[k]['precision']:.3f} R {agg[k]['recall']:.3f} F1 {agg[k]['f1']:.3f}", flush=True)
    report["settings"] = {"max_tokens": a.max_tokens, "workers": a.workers, "data": str(a.data), "limit": a.limit,
                          "prompt": "muse_shield.resolution.messages (system + worked example + numbered units)"}
    (out / "report.json").write_text(json.dumps(report, indent=1))
    print(f"recorded {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
