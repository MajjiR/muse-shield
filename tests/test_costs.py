from muse_shield.costs import run_cost


def test_token_cost_charges_cached_input_at_cached_rate():
    c = run_cost("muse-spark-1.3-contributor", {"in": 1_000_000, "cached_in": 600_000, "out": 500_000}, 10)
    assert c["basis"] == "tokens"
    assert abs(c["usd"] - (0.4 * 0.10 + 0.6 * 0.002 + 0.5 * 0.20)) < 1e-9


def test_gpu_time_cost_for_deployment_runs():
    gpu = {"accelerator": "NVIDIA_H200_141GB", "gpus_per_replica": 1, "replicas": 1}
    c = run_cost("accounts/fireworks/models/muse-glimmer-30b#accounts/me/deployments/x", {"in": 9, "out": 9}, 354.8, gpu)
    assert c["basis"] == "gpu_time" and abs(c["usd"] - 354.8 / 3600 * 8.0) < 1e-9
    assert c["detail"]["usd_per_gpu_hour"] == 8.0


def test_unknown_price_is_none_not_zero():
    assert run_cost("some-new-model", {"in": 10, "out": 10}, 1)["usd"] is None
