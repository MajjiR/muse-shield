"""What an eval run cost, recorded with its results.

Two billing models:
    tokens    Meta Model API (and Fireworks serverless): per-1M-token rates, cached input
              charged at the cached rate, reasoning tokens billed as output.
    gpu_time  a Fireworks on-demand deployment: billed per GPU-second while replicas run,
              so a run costs its wall-clock time x GPUs x hourly rate. The deployment keeps
              billing between runs too; that idle time is not attributed to any run.

Rates from the providers' pricing pages on 2026-11-03. Override with env vars if they change:
PRICE_<MODEL_ENV_NAME>_{IN,CACHED,OUT} or GPU_HOURLY_USD.
"""

from __future__ import annotations

import os

import httpx

TOKEN_PRICES = {  # USD per 1M tokens: (input, cached input, output)
    "muse-spark-1.3": (1.25, 0.15, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.002, 0.20),
    "muse-wonder-1.0": (4.00, 0.20, 20.00),
    # Azure AI Foundry, Global Standard (data building only). Flash: the published V4-Flash-0731 rate.
    "DeepSeek-V4-Pro": (1.74, 0.145, 3.48),
    "DeepSeek-V4-Flash": (0.44, 0.044, 1.32),
    # DeepSeek's own API (reported list prices; check platform.deepseek.com before budgeting)
    "deepseek-v4-pro": (1.74, 0.145, 3.48),
    "deepseek-flash": (0.30, 0.006, 1.20),
}
GPU_HOURLY = {  # USD per GPU-hour, Fireworks on-demand
    "NVIDIA_H200_141GB": 8.00,
    "NVIDIA_H100_80GB": 8.00,
    "NVIDIA_B200_180GB": 13.00,
}


def deployment_info(model: str, api_key: str, client: httpx.Client | None = None) -> dict | None:
    """For '<model>#accounts/<a>/deployments/<id>', read GPU type and count from the Fireworks API."""
    if "#" not in model or not api_key:
        return None
    path = model.split("#", 1)[1]
    try:
        r = (client or httpx).get(f"https://api.fireworks.ai/v1/{path}", headers={"Authorization": f"Bearer {api_key}"}, timeout=20)
        r.raise_for_status()
        d = r.json()
    except (httpx.HTTPError, ValueError):
        return None
    return {"deployment": path, "accelerator": d.get("acceleratorType"), "gpus_per_replica": d.get("acceleratorCount") or 1,
            "replicas": d.get("replicaCount") or d.get("minReplicaCount") or 1}


def run_cost(model: str, tokens: dict, seconds: float, gpu: dict | None = None) -> dict:
    """Cost record for one model's run: {usd, basis, detail}."""
    if "#" in model:
        gpu = gpu or {}
        rate = float(os.environ.get("GPU_HOURLY_USD") or GPU_HOURLY.get(gpu.get("accelerator") or "", 0) or 0) or None
        gpus = (gpu.get("gpus_per_replica") or 1) * (gpu.get("replicas") or 1)
        usd = seconds / 3600 * gpus * rate if rate else None
        return {"usd": usd, "basis": "gpu_time",
                "detail": {"seconds": round(seconds, 1), "gpus": gpus, "accelerator": gpu.get("accelerator"),
                           "usd_per_gpu_hour": rate, "note": "deployment idle time between runs is billed but not attributed"}}
    p = TOKEN_PRICES.get(model)
    env = model.upper().replace("-", "_").replace(".", "_")
    if os.environ.get(f"PRICE_{env}_IN") and os.environ.get(f"PRICE_{env}_OUT"):
        p = (float(os.environ[f"PRICE_{env}_IN"]), float(os.environ.get(f"PRICE_{env}_CACHED") or os.environ[f"PRICE_{env}_IN"]),
             float(os.environ[f"PRICE_{env}_OUT"]))
    if not p:
        return {"usd": None, "basis": "tokens", "detail": {"note": f"no price known for {model}"}}
    t_in, t_out, cached = tokens.get("in", 0), tokens.get("out", 0), tokens.get("cached_in", 0)
    usd = (t_in - cached) / 1e6 * p[0] + cached / 1e6 * p[1] + t_out / 1e6 * p[2]
    return {"usd": usd, "basis": "tokens",
            "detail": {"usd_per_1m": {"input": p[0], "cached_input": p[1], "output": p[2]}, **tokens}}
