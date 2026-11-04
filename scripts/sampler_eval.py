"""Score a training checkpoint (or base Glimmer) on our PII benchmarks by sampling, without a deployment.

    /Volumes/MajjiR/ai/venv-fwtrain/bin/python scripts/sampler_eval.py \
        --model-path <account>/<run-id>/step-150-<id>  (as save_weights_for_sampler returns) --task pii \
        --docs ../../runs/benchmarks/nemotron-test-500-s7.jsonl runs/eval/pii/tab-test.jsonl --tag pii1-s150

The Fireworks Training API can sample from a saved checkpoint (even after its run stopped), so there is
no on-demand deployment, no GPU-hour billing and no startup wait. It also doesn't take the training slot.
Each paragraph goes through the same prompt (`task_messages`), the Muse Glimmer chat renderer, and the
same contract check (`analysis.parse`, one retry) as the deployed backends. Results are recorded with
`save_run` under results/<eval>/ like any other run. Needs the SSD venv (fireworks SDK + cookbook).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
COOKBOOK = Path("/Volumes/MajjiR/ai/fw-cookbook")
sys.path[:0] = [str(COOKBOOK), str(REPO)]

from fireworks.training import tinker  # noqa: E402
from fireworks.training.sdk import FiretitanServiceClient  # noqa: E402
from training.renderer import get_text_content  # noqa: E402
from training.utils.supervised import build_renderer  # noqa: E402
from training.utils.tokenizers import load_tokenizer  # noqa: E402

from muse_shield.analysis import Analysis, ContractError, parse, split_sentences  # noqa: E402
from muse_shield.backends import Backend, task_messages  # noqa: E402
from muse_shield.benchmarks.nemotron import Doc  # noqa: E402
from muse_shield.benchmarks.run import render, run_backend  # noqa: E402
from muse_shield.config import load_env  # noqa: E402
from muse_shield.results import git_version, save_run, sha256  # noqa: E402

BASE = "accounts/fireworks/models/muse-glimmer-30b"
TOKENIZER = "meta-models/Muse-Glimmer-30B"


class SamplerBackend(Backend):
    def __init__(self, sampler, renderer, task: str, model: str, max_tokens: int):
        self.sampler, self.renderer, self.task, self.model, self.max_tokens = sampler, renderer, task, model, max_tokens
        self.name = "glimmer-sampler"

    def _sample(self, messages: list[dict]) -> tuple[str, dict]:
        prompt = self.renderer.build_generation_prompt(messages)
        out = self.sampler.sample(prompt=prompt, num_samples=1, sampling_params=tinker.SamplingParams(
            max_tokens=self.max_tokens, temperature=0.0, stop=self.renderer.get_stop_sequences())).result()
        tokens = out.sequences[0].tokens
        msg, termination = self.renderer.parse_response(tokens)
        n_prompt = len(prompt.to_ints()) if hasattr(prompt, "to_ints") else 0
        return get_text_content(msg) or "", {"prompt_tokens": n_prompt, "completion_tokens": len(tokens), "termination": str(termination)}

    def analyze_one(self, paragraph: str, known_labels=None) -> Analysis:
        sentences = split_sentences(paragraph) or [paragraph]
        messages = task_messages(self.task, sentences)
        usage: dict = {}
        t0, error = time.perf_counter(), ""
        for attempt in (1, 2):
            raw, u = self._sample(messages)
            for k in ("prompt_tokens", "completion_tokens"):
                usage[k] = usage.get(k, 0) + u[k]
            try:
                res = parse(raw, paragraph, sentences)
                res.attempts, res.usage, res.latency_ms = attempt, usage, (time.perf_counter() - t0) * 1000
                return res
            except ContractError as exc:
                error = str(exc)
                messages = messages + [{"role": "assistant", "content": raw},
                                       {"role": "user", "content": f"That output broke the contract ({error}). Reply with only the corrected JSON object."}]
        bad = Analysis(paragraph, sentences)
        bad.valid, bad.error, bad.attempts, bad.usage, bad.latency_ms = False, error, 2, usage, (time.perf_counter() - t0) * 1000
        return bad

    def analyze(self, paragraphs, known_labels=None):
        return [self.analyze_one(p) for p in paragraphs]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-path", default="", help="sampler checkpoint path; empty = base Glimmer")
    ap.add_argument("--task", default="pii", choices=["pii", "full"])
    ap.add_argument("--docs", nargs="+", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=32)
    ap.add_argument("--max-tokens", type=int, default=1536)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--no-record", action="store_true")
    a = ap.parse_args(argv)
    load_env()
    tok = load_tokenizer(TOKENIZER)
    renderer = build_renderer(tok, TOKENIZER, "muse_glimmer")
    service = FiretitanServiceClient(api_key=os.environ["FIREWORKS_API_KEY"], base_url="https://api.fireworks.ai/training/v1/serverless")
    try:
        sampler = service.create_sampling_client(model_path=a.model_path, tokenizer=tok) if a.model_path \
            else service.create_sampling_client(base_model=BASE, tokenizer=tok)
        backend = SamplerBackend(sampler, renderer, a.task, a.model_path or BASE, a.max_tokens)
        for path in a.docs:
            docs = [Doc.from_dict(json.loads(l)) for l in path.read_text().splitlines() if l.strip()]
            docs = docs[: a.limit] if a.limit else docs
            started, git = time.time(), git_version()
            print(f"{path.name}: {len(docs)} docs …", flush=True)
            report, preds = run_backend(backend, docs, a.workers)
            report["cost_usd"], report["cost"] = None, {"basis": "training-api sampling (per token; rate not published here)"}
            md = render([report], len(docs))
            print(md, flush=True)
            if not a.no_record:
                eval_name = "nemotron-pii" if path.name.startswith("nemotron-test") else f"pii-{path.stem}"
                out = save_run(eval_name, f"{a.tag}", [report], {report["backend"]: preds},
                               settings={report["backend"]: {"model": backend.model, "task": a.task, "max_tokens": a.max_tokens,
                                                             "workers": a.workers, "via": "training-api sampler"}},
                               dataset={"name": str(path), "docs": len(docs), "sample_sha256": sha256(path), "task": a.task},
                               compare_md=md, when=started, git=git)
                print(f"recorded {out}", flush=True)
        sampler.close()
    finally:
        service.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
